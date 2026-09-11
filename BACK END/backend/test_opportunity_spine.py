"""Synthetic-only Opportunity Spine adversarial contracts; no native boundaries."""
from copy import deepcopy
from datetime import timedelta
import json
import os
from pathlib import Path
import unittest

from opportunity_spine_contract import OfflineSession, authority, receipt, schedule, verify
from opportunity_spine_signals import POLICY, Signals, Promotions, compare_yahoo
from opportunity_spine_factory import (AGENTS, MODELS, PROVIDERS, routing, adjudicate,
                                       capacity, final_session, projection, scan_receipt)
from provider_gateway_contract import content_hash, utc

SOURCE = 'b'*40
ROOT = str(Path(os.environ['IIOS_GATEWAY_TEST_ROOT']) / 'synthetic-day')
UNIVERSE = {'symbols': ['SPY', 'QQQ']+[f'S{i:04d}' for i in range(515)]}
CALENDAR = {'calendar': 'XNYS', 'session': '2026-09-14', 'open': '2026-09-14T13:30:00+00:00',
            'close': '2026-09-14T20:00:00+00:00'}


def make(mode='FULL_OPPORTUNITY_RADAR'):
    u,c=deepcopy(UNIVERSE),deepcopy(CALENDAR)
    p=schedule(u,content_hash(u),c,content_hash(c),mode=mode,root=ROOT)
    s=OfflineSession(p,content_hash(p),universe=u,universe_hash=content_hash(u),
                     calendar=c,calendar_hash=content_hash(c),root=ROOT,source=SOURCE)
    return p,s


def payload(symbols, stamp, close='100'):
    return {'endpoint':'REALTIME_BULK_QUOTES','data':[{'symbol':s,'timestamp':stamp,
            'open':'100','high':'110','low':'90','close':close,'volume':'1000'} for s in symbols]}


def attempt(s, *, engine=None, close='100', mutate=None, elapsed=1):
    _,batch,start,_,symbols=s._row()
    offset=0 if s.slot==0 else (0,21,42,63,84,105)[batch]
    at=(utc(start)+timedelta(seconds=offset)).isoformat()
    reservation=s.reserve(at);p=payload(symbols,at,close)
    if mutate:mutate(p)
    end=(utc(at)+timedelta(seconds=elapsed)).isoformat()
    if engine:
        return engine.consume(s,p,response_at=end,reservation_hash=content_hash(reservation))
    return s.complete(p,response_at=end,reservation_hash=content_hash(reservation))


def signal_fixture(scan=0, detected=False):
    return receipt('signals', {'scan':scan,'mode':'FULL_OPPORTUNITY_RADAR','rows':[
        {'symbol':s,'freshness':'WITHIN_AGE_BOUND','detected':detected} for s in UNIVERSE['symbols']]},
        {'schedule':'a'*64,'policy':content_hash(POLICY)},source=SOURCE)


def candidates(signals, score=45, news=2):
    sh=content_hash(signals)
    admission=receipt('legacy-promotion',{'rows':[{'symbol':r['symbol'],'score':score,'news_count':news,
                     'quote_ok':True,'eligible_for_promotion':True} for r in signals['data']['rows']]},
                     {'signals':sh},source=SOURCE)
    promoter=Promotions(POLICY,content_hash(POLICY))
    value=promoter.select(signals,sh,parents=signals['parents'],eligibility=admission,
                          eligibility_hash=content_hash(admission),source=SOURCE,now='2026-09-14T13:35:30Z')
    return value,admission,promoter


def case_fixture(*, provider_failure=None, veto=False, decision='APPROVE', omit=()):
    c,_,_=candidates(signal_fixture(detected=True))
    r=routing(c,content_hash(c),parents=c['parents'],candidate_id=c['data']['rows'][0]['candidate_id'],source=SOURCE)
    rh=content_hash(r);parents={'routing':rh};stages={};pins={}
    for name in list(PROVIDERS)+list(AGENTS)+list(MODELS)+['committee','risk']:
        if name in omit:continue
        disposition='VETO' if name=='risk' and veto else 'ALLOW' if name=='risk' else decision if name=='committee' else 'WATCH' if name=='Grok' else 'NO_TRADE'
        d={'case_id':r['data']['case_id'],'status':'FAILED' if name==provider_failure else 'PASS',
           'decision':disposition,'evidence_admitted':name in PROVIDERS,'deterministic':name=='risk'}
        stage=receipt(name,d,parents,source=SOURCE)
        stages[name]=stage;pins[name]=content_hash(stage);parents={**parents,name:pins[name]}
    result=adjudicate(r,rh,route_parents=r['parents'],stages=stages,expected=pins,source=SOURCE)
    return result,r,stages,pins


class OpportunityTests(unittest.TestCase):
    def test_schedule_all_79_and_475(self):
        p,_=make()
        self.assertEqual((len(p['scans']),p['collection_requests'],p['proposed_request_ceiling']),(79,474,475))
        self.assertEqual(p['preflight']['valid_from'],'2026-09-14T13:20:00+00:00')
        self.assertEqual(p['preflight']['expires_at'],'2026-09-14T13:25:00+00:00')
        self.assertEqual(p['scans'][-1]['start'],'2026-09-14T20:00:30+00:00')
        for i,r in enumerate(p['scans']):
            self.assertEqual([len(b) for b in r['batches']],[100]*5+[17])
            self.assertEqual(sum(r['batches'],[]),UNIVERSE['symbols'])
            if i:self.assertEqual(p['scans'][i-1]['end'],r['start'])
        self.assertFalse(p['allowance_released'])

    def test_baseline_preserved(self):
        p,_=make('BASELINE_ONLY')
        self.assertEqual((len(p['scans']),p['collection_requests'],p['proposed_request_ceiling']),(3,18,19))
        self.assertEqual(p['scans'][0]['end'],'2026-09-14T13:32:10+00:00')
        self.assertEqual(p['scans'][1]['start'],'2026-09-14T16:30:00+00:00')

    def test_plan_mutations_and_universe_identity(self):
        p,_=make()
        for change in ('symbol','order','ceiling'):
            v=deepcopy(p)
            if change=='symbol':v['scans'][0]['batches'][0][0]='OTHER'
            elif change=='order':v['scans'][0]['batches'].reverse()
            else:v['proposed_request_ceiling']=476
            with self.assertRaises(ValueError):OfflineSession(v,content_hash(v),universe=UNIVERSE,universe_hash=content_hash(UNIVERSE),calendar=CALENDAR,calendar_hash=content_hash(CALENDAR),root=ROOT,source=SOURCE)
        for members in [UNIVERSE['symbols'][:-1],UNIVERSE['symbols'][:-1]+['SPY']]:
            with self.assertRaises(ValueError):schedule({'symbols':members},content_hash({'symbols':members}),CALENDAR,content_hash(CALENDAR),mode='FULL_OPPORTUNITY_RADAR',root=ROOT)

    def test_missing_preflight_reservation_and_overlap(self):
        _,s=make()
        with self.assertRaises(ValueError):s.reserve('2026-09-14T13:30:30Z')
        _,s=make();s.reserve('2026-09-14T13:20:00Z')
        with self.assertRaises(ValueError):s.reserve('2026-09-14T13:20:01Z')
        self.assertEqual(s.final()['data']['status'],'FAILED')

    def test_rate_three_starts_and_boundary(self):
        _,s=make();attempt(s)
        for second in (0,1,2):
            stamp=f'2026-09-14T13:30:{30+second:02d}Z';r=s.reserve(stamp)
            s.complete(payload(s._row()[-1],stamp),response_at=stamp,reservation_hash=content_hash(r))
        with self.assertRaises(ValueError):s.reserve('2026-09-14T13:30:33Z')
        s.reserve('2026-09-14T13:31:30Z')
        self.assertEqual(len(s.starts),5)

    def test_missing_partial_duplicate_unexpected_reordered_schema(self):
        mutations=[lambda p:p['data'].pop(),lambda p:p['data'].append(p['data'][0]),
                   lambda p:p['data'][0].update(symbol='OTHER'),lambda p:p['data'].reverse(),
                   lambda p:p.update(new_schema='unsupported'),lambda p:p['data'][0].pop('close')]
        for mutate in mutations:
            _,s=make();r=attempt(s,mutate=mutate)
            self.assertEqual(r['data']['status'],'FAILED')
            with self.assertRaises(ValueError):s.reserve('2026-09-14T13:30:30Z')

    def test_missing_stale_future_naive_conflicting_timestamps(self):
        for stamp in [None,'2026-09-11T13:20:00Z','2026-09-14T14:00:00Z','2026-09-14 13:20:00','bad']:
            _,s=make();r=attempt(s,mutate=lambda p:p['data'][0].update(timestamp=stamp))
            self.assertEqual(r['data']['status'],'FAILED')
        _,s=make();r=attempt(s,elapsed=-1);self.assertEqual(r['data']['status'],'FAILED')

    def test_size_timeout_and_expired_cycle(self):
        _,s=make();r=attempt(s,mutate=lambda p:p.update(message='x'*1_000_001));self.assertEqual(r['data']['status'],'FAILED')
        _,s=make();r=attempt(s,elapsed=21);self.assertEqual(r['data']['status'],'FAILED')
        _,s=make();attempt(s)
        with self.assertRaises(ValueError):s.reserve('2026-09-14T13:35:30Z')
        self.assertTrue(s.stopped)

    def test_interruption_no_retry_and_wrong_reservation(self):
        _,s=make();r=s.reserve('2026-09-14T13:20:00Z')
        with self.assertRaises(ValueError):s.complete({},response_at='2026-09-14T13:20:01Z',reservation_hash='0'*64)
        self.assertEqual(s.pending,r)
        self.assertTrue(s.interrupt()['data']['ambiguous_reservation_retained'])
        with self.assertRaises(ValueError):s.reserve('2026-09-14T13:20:02Z')

    def test_signal_threshold_persistence_reversal_missing_fields(self):
        _,s=make();e=Signals(POLICY,content_hash(POLICY));attempt(s,engine=e)
        scans=[]
        for close in ('100','101','102.01','100'):
            out=None
            for _ in range(6):_,out=attempt(s,engine=e,close=close)
            scans.append(out['data']['rows'][0])
        self.assertIsNone(scans[0]['five_minute_return_percent'])
        self.assertEqual(scans[1]['five_minute_return_percent'],1)
        self.assertTrue(scans[1]['detected']);self.assertTrue(scans[2]['persistent'])
        self.assertTrue(scans[3]['reversal']);self.assertEqual(scans[3]['persistence'],1)
        self.assertIsNone(scans[1]['gap_percent']);self.assertIsNone(scans[1]['relative_volume'])
        self.assertEqual(scans[1]['relative_strength_qqq'],0)
        self.assertNotIn('close',scans[1]);self.assertNotIn('price',scans[1])

    def test_signal_below_threshold_and_sector_data(self):
        _,s=make();sector={'version':'governed-sectors-v1','members':{'SPY':'BROAD','QQQ':'BROAD'}}
        e=Signals(POLICY,content_hash(POLICY),sectors=sector,sectors_hash=content_hash(sector));attempt(s,engine=e)
        for close in ('100','100.99'):
            out=None
            for _ in range(6):_,out=attempt(s,engine=e,close=close)
        self.assertFalse(out['data']['rows'][0]['detected'])
        self.assertEqual(out['data']['rows'][0]['sector_divergence'],0)
        with self.assertRaises(ValueError):Signals(POLICY,'0'*64)

    def test_yahoo_agreement_only_disagreement_failure_missing_time(self):
        for status in ('PASS','FAILED','UNAVAILABLE'):
            doc=receipt('yahoo',{'scan':0,'status':status,'symbols':['SPY','MU'],
                        'provider_timestamp':None,'recorded_requests':3},{'scan':'a'*64},source=SOURCE)
            result=compare_yahoo(['SPY','QQQ'],doc,content_hash(doc),scan=0,scan_parent='a'*64,source=SOURCE)
            self.assertEqual(result['status'],status);self.assertEqual(result['timestamp_status'],'MISSING')
            if status=='PASS':
                self.assertEqual({r['comparison'] for r in result['rows']},{'AGREEMENT','ALPHA_ONLY','YAHOO_ONLY_ALPHA_EVIDENCE_REQUIRED'})
            else:self.assertEqual(result['rows'],[])
        self.assertIsNone(compare_yahoo([],None,None,scan=0,scan_parent='a'*64,source=SOURCE)['requests'])

    def test_candidate_limits_duplicate_and_legacy_boundaries(self):
        sig=signal_fixture(detected=True);c,admission,promoter=candidates(sig)
        self.assertEqual(len(c['data']['rows']),5);self.assertEqual(sum(r['case_selected'] for r in c['data']['rows']),2)
        second=promoter.select(sig,content_hash(sig),parents=sig['parents'],eligibility=admission,
                              eligibility_hash=content_hash(admission),source=SOURCE,now='2026-09-14T13:40:30Z')
        self.assertFalse(set(r['symbol'] for r in c['data']['rows']) & set(r['symbol'] for r in second['data']['rows']))
        for score,news in [(44.99,2),(45,1)]:self.assertEqual(candidates(sig,score,news)[0]['data']['rows'],[])
        self.assertEqual(candidates(signal_fixture())[0]['data']['rows'],[])

    def test_required_optional_isolation_and_not_run(self):
        blocked,*_=case_fixture(provider_failure='BIGDATA')
        okay,*_=case_fixture(provider_failure='MASSIVE')
        self.assertTrue(blocked['data']['evidence_block']);self.assertFalse(okay['data']['evidence_block'])
        pending,*_=case_fixture(omit=('BIGDATA','Grok'))
        self.assertEqual(pending['data']['stages']['BIGDATA']['status'],'NOT_RUN')
        self.assertEqual(pending['data']['stages']['Grok']['status'],'NOT_RUN')
        self.assertEqual(pending['data']['decision'],'EVIDENCE_BLOCK')

    def test_committee_approval_then_risk_veto_and_disagreement(self):
        c,*_=case_fixture(veto=True)
        self.assertEqual(c['data']['stages']['committee']['decision'],'APPROVE')
        self.assertEqual(c['data']['decision'],'NO_TRADE');self.assertTrue(c['data']['risk_veto'])
        self.assertNotEqual(c['data']['disagreement']['Grok'],c['data']['disagreement']['Gemini'])
        for flag in authority():self.assertIs(c['authority'][flag],False)
        self.assertEqual(case_fixture(decision='WATCH')[0]['data']['decision'],'WATCH')
        self.assertEqual(case_fixture(decision='NO_TRADE')[0]['data']['decision'],'NO_TRADE')

    def test_stage_replay_parents_and_model_truth_rejected(self):
        _,r,stages,pins=case_fixture()
        for mutate in [lambda d:d['data'].update(case_id='0'*64),lambda d:d['parents'].update(routing='0'*64),
                       lambda d:d['data'].update(evidence_admitted=True)]:
            changed=deepcopy(stages);d=changed['policy'];mutate(d)
            body={k:v for k,v in d.items() if k!='receipt_hash'};d['receipt_hash']=content_hash(body)
            expected={**pins,'policy':content_hash(d)}
            with self.assertRaises(ValueError):adjudicate(r,content_hash(r),route_parents=r['parents'],stages=changed,expected=expected,source=SOURCE)

    def test_receipt_tampering_and_authority(self):
        d=receipt('test',{'status':'PASS'},{'parent':'a'*64},source=SOURCE)
        for flag in authority():
            changed=deepcopy(d);changed['authority'][flag]=True
            with self.assertRaises(ValueError):verify(changed,content_hash(changed),kind='test',parents=d['parents'],source=SOURCE)
        with self.assertRaises(ValueError):verify(d,content_hash(d),kind='test',parents={'parent':'b'*64},source=SOURCE)

    def test_cost_capacity(self):
        p,_=make();v=capacity(p,yahoo_recorded_requests=None)
        self.assertEqual(v['alpha_proposed_total'],475);self.assertEqual(v['alpha_response_byte_upper_bound'],475_000_000)
        self.assertEqual(v['max_cases_session_upper_bound'],158);self.assertEqual(v['max_promotions_session_upper_bound'],395)
        self.assertEqual(v['model_calls_session_upper_bound'],1896)
        self.assertIsNone(v['monetary_cost']);self.assertFalse(v['allowance_released'])

    def test_all_475_reservations_final_no_candidates_and_projection(self):
        p,s=make();engine=Signals(POLICY,content_hash(POLICY));attempt(s,engine=engine)
        scans={};scan_pins={}
        for i in range(79):
            sig=None
            for _ in range(6):r,sig=attempt(s,engine=engine)
            self.assertEqual(r['data']['status'],'PASS')
            c,_,_=candidates(sig)
            y=receipt('yahoo',{'scan':i,'status':'PASS','symbols':[],'provider_timestamp':None,'recorded_requests':3},
                      {'scan':content_hash(sig)},source=SOURCE)
            comparison=compare_yahoo([],y,content_hash(y),scan=i,scan_parent=content_hash(sig),source=SOURCE)
            doc=scan_receipt(sig,content_hash(sig),c,content_hash(c),comparison,signal_parents=sig['parents'],
                             candidate_parents=c['parents'],schedule_hash=content_hash(p),source=SOURCE)
            scans[str(i)]=doc;scan_pins[str(i)]=content_hash(doc)
        self.assertEqual(len(s.starts),475)
        with self.assertRaises(ValueError):s.reserve('2026-09-14T20:04:00Z')
        col=s.final()
        result=final_session(col,content_hash(col),schedule_hash=content_hash(p),scans=scans,scan_hashes=scan_pins,
                             cases={},case_hashes={},source=SOURCE,backend_identity='c'*64,frontend_identity='d'*64)
        self.assertEqual(result['data']['status'],'GREEN')
        view=projection(result,content_hash(result),parents=result['parents'],source=SOURCE,backend_identity='c'*64,frontend_identity='d'*64)
        self.assertEqual(view['case_count'],0);self.assertFalse(view['armed'])
        # Cross-language contract fixture written only beneath the authorized synthetic test root.
        (Path(os.environ['IIOS_GATEWAY_TEST_ROOT'])/'projection.json').write_text(json.dumps({'view':view,'hash':content_hash(view)}))
        with self.assertRaises(ValueError):projection(result,content_hash(result),parents=result['parents'],source=SOURCE,backend_identity='0'*64,frontend_identity='d'*64)
        partial=deepcopy(scans);partial.pop('78')
        red=final_session(col,content_hash(col),schedule_hash=content_hash(p),scans=partial,
                          scan_hashes={k:v for k,v in scan_pins.items() if k!='78'},cases={},case_hashes={},source=SOURCE,
                          backend_identity='c'*64,frontend_identity='d'*64)
        self.assertEqual(red['data']['status'],'RED')
        warn=deepcopy(scans);d=warn['0']['data']
        yd=deepcopy(d['yahoo']['receipt']['data']);yd['status']='FAILED'
        yr=receipt('yahoo',yd,{'scan':d['signal_parent']},source=SOURCE)
        comparison=compare_yahoo([],yr,content_hash(yr),scan=0,scan_parent=d['signal_parent'],source=SOURCE)
        warn['0']=scan_receipt(d['signals'],d['signal_parent'],d['candidates'],d['candidate_parent'],comparison,
                               signal_parents=d['signals']['parents'],candidate_parents=d['candidates']['parents'],schedule_hash=content_hash(p),source=SOURCE)
        yellow=final_session(col,content_hash(col),schedule_hash=content_hash(p),scans=warn,
                             scan_hashes={**scan_pins,'0':content_hash(warn['0'])},cases={},case_hashes={},source=SOURCE,
                             backend_identity='c'*64,frontend_identity='d'*64)
        self.assertEqual(yellow['data']['status'],'YELLOW')
