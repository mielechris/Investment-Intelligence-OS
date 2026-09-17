import copy,unittest
from iios_native_conductor import QualificationFailure
from iios_native_seal_binding import image_parent

class SealBindingTests(unittest.TestCase):
    def setUp(self):
        self.receipt={'schema':'iios-resource-seal-receipt-v2','original_files':{'image':{'path':'image','sha256':'before'}},
          'derived_files':{'image':{'path':'image','sha256':'after'}},'signing_evidence_parent':'parent',
          'signing_evidence':{'pre_transform':[{'path':'image','sha256':'before'}],'post_sign':[{'path':'image','sha256':'after'}]}}
        self.checked=[]
    def validate(self,value,parent):self.checked.append((value,parent))
    def verify(self,**kw):
        args=dict(name='image',original_hash='before',final_hash='after',receipt=self.receipt,validate_signing=self.validate);args.update(kw)
        return image_parent(**args)
    def test_signed_image_uses_signed_parent(self):self.assertEqual(self.verify(),'after');self.assertEqual(len(self.checked),1)
    def test_changed_unsigned_image_rejected(self):
        with self.assertRaises(QualificationFailure):self.verify(name='unchanged')
    def test_unchanged_image_retains_original(self):self.assertEqual(self.verify(name='unchanged',final_hash='before'),'before')
    def test_each_parent_mutation_rejected(self):
        cases=[('original_files','sha256'),('derived_files','sha256'),('original_files','path'),('derived_files','path')]
        for key,field in cases:
            r=copy.deepcopy(self.receipt);r[key]['image'][field]='altered'
            with self.subTest(key=key,field=field),self.assertRaises(QualificationFailure):self.verify(receipt=r)
    def test_transform_parents_both_required(self):
        for key in ('pre_transform','post_sign'):
            r=copy.deepcopy(self.receipt);r['signing_evidence'][key][0]['sha256']='altered'
            with self.subTest(key=key),self.assertRaises(QualificationFailure):self.verify(receipt=r)
    def test_existing_signature_validator_required(self):
        def denied(*args):raise ValueError('RUNTIME_SIGNING_EVIDENCE')
        with self.assertRaisesRegex(ValueError,'RUNTIME_SIGNING_EVIDENCE'):self.verify(validate_signing=denied)
    def test_missing_or_swapped_members_rejected(self):
        r=copy.deepcopy(self.receipt);r['derived_files']['other']=r['derived_files'].pop('image')
        with self.assertRaises(QualificationFailure):self.verify(receipt=r)

if __name__=='__main__':unittest.main()
