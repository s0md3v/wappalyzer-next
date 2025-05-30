import ssl

def get_certIssuer(response):
    #  TODO: This doesn't work right now
    try:
        cert_info_raw = response.raw.connection.sock.getpeercert(True)
        pem_cert = ssl.DER_cert_to_PEM_cert(cert_info_raw)
        cert_info = response.raw.connection.sock.getpeercert()
        if 'issuer' in cert_info:
            for array in cert_info['issuer']:
                if 'organizationName' in array[0]:
                    return array[1]
    except Exception as e:
        pass
    return ''