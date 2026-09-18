"""Existing synthetic-only certificate recipe; caller supplies bounded effects.

No effect occurs on import. No real credential or provider input is accepted.
"""
from pathlib import Path


def create_dummy_tls(config,fixture,*,command,put):
    config=Path(config);fixture=Path(fixture)
    put(config, b'[req]\nprompt=no\ndistinguished_name=dn\nx509_extensions=ext\n'
        b'[dn]\nCN=Alpha Radar SYNTHETIC TEST ONLY\n[ext]\nsubjectAltName=IP:127.0.0.1\n'
        b'basicConstraints=critical,CA:TRUE\nkeyUsage=critical,digitalSignature,keyEncipherment,keyCertSign\n'
        b'extendedKeyUsage=serverAuth\n')
    command(['/usr/bin/openssl','req','-x509','-newkey','rsa:2048','-nodes','-sha256','-days','1',
             '-config',str(config),'-keyout',str(fixture/'private-key.pem'),'-out',str(fixture/'certificate.pem')])
    return fixture/'certificate.pem',fixture/'private-key.pem'
