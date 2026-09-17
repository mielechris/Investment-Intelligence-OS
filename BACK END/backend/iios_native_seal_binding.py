"""Validate signed image hashes against the existing bottom-up seal evidence.

An original unsigned wheel hash is never silently treated as its signed hash.
This supplements, and cannot replace, native signatures, load-command checks,
complete runtime inventory verification and verify_seal_delta.
"""
from iios_native_conductor import require, STAGES


def image_parent(name,original_hash,final_hash,receipt,*,validate_signing):
    stage=STAGES[5]
    require(receipt.get('schema')=='iios-resource-seal-receipt-v2',stage,'FINAL_SIGNING_RECEIPT')
    validate_signing(receipt['signing_evidence'],receipt['signing_evidence_parent'])
    original=receipt['original_files'];derived=receipt['derived_files']
    require(set(original)==set(derived),stage,'FINAL_SEAL_IMAGE_SET')
    if name not in derived:
        require(final_hash==original_hash,stage,'FINAL_IMAGE_SUBSTITUTION','ORIGINAL_IMAGE','ALTERED_IMAGE')
        return original_hash
    require(original[name]['path']==derived[name]['path']==name and original[name]['sha256']==original_hash,
            stage,'FINAL_IMAGE_ORIGINAL_PARENT','PINNED_ORIGINAL','MISMATCH')
    require(derived[name]['sha256']==final_hash,stage,'FINAL_IMAGE_SIGNED_PARENT','PINNED_SIGNED','MISMATCH')
    if name!='Python':
        before={row['path']:row for row in receipt['signing_evidence']['pre_transform']}
        after={row['path']:row for row in receipt['signing_evidence']['post_sign']}
        require(name in before and name in after and before[name]['sha256']==original_hash and after[name]['sha256']==final_hash,
                stage,'FINAL_IMAGE_TRANSFORM_PARENT','PINNED_TRANSFORM','MISMATCH')
    return derived[name]['sha256']
