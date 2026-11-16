"""Read-only public HTTPS readiness. No login secrets, model calls or initialization."""
import argparse
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def check(origin,open_request=None):
    from deploy import https_url
    origin=https_url(origin,True)
    if open_request is None:
        open_request=urllib.request.build_opener(NoRedirect(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context())).open
    def get(url):
        try:return open_request(urllib.request.Request(url,method='GET'),timeout=15)
        except urllib.error.HTTPError as response:return response
    issues=[]
    with get(origin+'/api/health') as r:
        if r.status!=200 or json.loads(r.read(1024))!={'status':'ok'}:issues.append('health_failed')
    with get(origin+'/api/config') as r:
        value=json.loads(r.read(4096))
        if r.status!=200 or value.get('demo_mode') is not False:issues.append('demo_or_config_failed')
    with get(origin+'/api/export') as r:
        if r.status!=401:issues.append('anonymous_export_not_denied')
    parsed=urllib.parse.urlsplit(origin)
    with get('http://'+parsed.netloc+'/') as r:
        location=r.headers.get('Location','')
        if r.status not in (301,302,307,308) or location.rstrip('/')!=origin:issues.append('http_https_redirect_failed')
    return {'status':'ok' if not issues else 'failed','issues':issues,'tls_verification':True,
            'login_cookie_and_wechat':'still_requires_authenticated_device_acceptance','model_calls':0}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--origin',required=True);a=p.parse_args()
    try:result=check(a.origin)
    except Exception:result={'status':'failed','issues':['tls_network_or_protocol_failed'],'model_calls':0}
    print(json.dumps(result));return 0 if result['status']=='ok' else 1


if __name__=='__main__':raise SystemExit(main())
