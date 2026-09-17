import unittest
from iios_native_terminal import *

class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.binding={'host':{'system':'Darwin'},'selectors':{'TERM_PROGRAM':'Apple_Terminal'},'terminal_executable':'/Applications/Terminal.app/Contents/MacOS/Terminal'}
        self.env={'TERM_PROGRAM':'Apple_Terminal'};self.host={'system':'Darwin'};self.queries=[]
    def query(self,argv):
        self.queries.append(argv)
        if argv[-1]=='ppid=':return '101'
        return '/bin/zsh' if argv[3]=='100' else self.binding['terminal_executable']
    def run_admission(self,**kw):
        args=dict(environment=self.env,ttys=[True]*3,host=self.host,parent_pid=100,query=self.query,clock=lambda:1,deadline=10);args.update(kw)
        return admit_terminal(self.binding,**args)
    def test_exact_apple_terminal(self):self.assertTrue(all(self.run_admission().values()));self.assertEqual(len(self.queries),3)
    def test_vscode_codex_and_no_tty(self):
        for env,ttys,predicate in [({'TERM_PROGRAM':'vscode'},[True]*3,'TERMINAL_APPLICATION'),({'TERM_PROGRAM':'Apple_Terminal','CODEX_THREAD_ID':'redacted'},[True]*3,'TERMINAL_FORBIDDEN_MARKERS'),(self.env,[True,False,True],'TERMINAL_TTY')]:
            with self.subTest(predicate=predicate),self.assertRaises(QualificationFailure) as c:self.run_admission(environment=env,ttys=ttys)
            self.assertEqual(c.exception.detail['predicate'],predicate)
    def test_missing_ancestry(self):
        with self.assertRaises(QualificationFailure):self.run_admission(query=lambda argv:'/bin/zsh' if argv[-1]=='comm=' else '1')
    def test_changed_host_and_environment(self):
        with self.assertRaises(QualificationFailure):self.run_admission(host={})
        self.binding['selectors']['TERM']='xterm-256color'
        with self.assertRaises(QualificationFailure) as c:self.run_admission()
        self.assertEqual(c.exception.detail['predicate'],'TERMINAL_ENVIRONMENT_BINDING')
    def test_ancestry_substring_rejected(self):
        with self.assertRaises(QualificationFailure):self.run_admission(query=lambda argv:self.binding['terminal_executable']+' fake')
    def test_deadline_no_queries(self):
        with self.assertRaises(QualificationFailure):self.run_admission(clock=lambda:10)
        self.assertFalse(self.queries)
    def test_ancestry_pid_cycle(self):
        with self.assertRaises(QualificationFailure) as c:self.run_admission(query=lambda argv:'/bin/zsh' if argv[-1]=='comm=' else '100')
        self.assertEqual(c.exception.detail['predicate'],'TERMINAL_ANCESTRY_PID')

class AuditTests(unittest.TestCase):
    def setUp(self):self.guard=AuditBoundary(read_paths=['/approved/input'],write_root='/exclusive/root',stage=STAGES[1])
    def test_exact_read_and_write_boundaries(self):
        self.guard('open',('/approved/input','r',0));self.guard('open',('/exclusive/root/result','w',os.O_WRONLY))
        for path,mode,flags in [('/approved/input','w',os.O_WRONLY),('/other','r',0),('relative','w',os.O_WRONLY),('/exclusive/root/../escape','w',os.O_WRONLY)]:
            with self.assertRaises(QualificationFailure):self.guard('open',(path,mode,flags))
    def test_signals_network_and_spawn_denied(self):
        for event in ('os.kill','os.killpg','socket.connect','os.posix_spawn','os.fork','os.exec'):
            with self.assertRaises(QualificationFailure):self.guard(event,())
    def test_pinned_command_only(self):
        args=('/bin/ps',('/bin/ps','-p','35731'),'/exclusive/root',{'LC_ALL':'C'})
        with self.assertRaises(QualificationFailure):self.guard('subprocess.Popen',args)
        self.guard.command=args;self.guard('subprocess.Popen',args)
        with self.assertRaises(QualificationFailure):self.guard('subprocess.Popen',(args[0],args[1],args[2],{}))
    def test_policy_denial_retains_no_raw_path(self):
        with self.assertRaises(QualificationFailure):self.guard('open',('/exclusive/root/credentials/private','r',0))
        self.assertEqual(self.guard.last_denial['errno_category'],'AUDIT_POLICY');self.assertNotIn('private',str(self.guard.last_denial))

if __name__=='__main__':unittest.main()
