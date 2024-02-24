import json
import requests
import os

# from https://gist.github.com/FluffyDietEngine/94c0137445555a418ac9f332edfa6f4b
from requests import Session
from requests import adapters
from urllib3 import poolmanager
from ssl import create_default_context, Purpose, CERT_NONE

from definitions import ROOT_DIR
from downloader.exceptions import AuthenticationError, IneligibleError

class CustomHttpAdapter (adapters.HTTPAdapter):
    def __init__(self, ssl_context=None, **kwargs):
        self.ssl_context = ssl_context
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False):
        self.poolmanager = poolmanager.PoolManager(
            num_pools=connections, maxsize=maxsize,
            block=block, ssl_context=self.ssl_context)

def ssl_supressed_session():
    ctx = create_default_context(Purpose.SERVER_AUTH)
    # to bypass verification after accepting Legacy connections
    ctx.check_hostname = False
    ctx.verify_mode = CERT_NONE
    # accepting legacy connections
    ctx.options |= 0x4    
    session = Session()
    session.mount('https://', CustomHttpAdapter(ctx))
    return session

class Client:
  def __init__(self, site, **kwargs):
    cfg = self.parse_cfg(site)
    self.session = ssl_supressed_session()
    self.session.headers.update({
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; '
        'rv:67.0) Gecko/20100101 Firefox/67.0',
      'Referer': cfg['referer']
    })
    self.base = cfg['base']

  def parse_cfg(self, site):
    with open(os.path.join(ROOT_DIR,'config.json')) as f:
      cfg = json.load(f)
    return cfg[site]

  def fix_json(self, j):
    return json.loads(j.rstrip()[21:-2])

  def api_call(self, epoint, method, **kwargs):
    if method == "user.site.login":
      params = {
        'username': kwargs['email'],
        'pw': kwargs['pwd']
      }
    elif method == "user.site.getSubscriberInfo":
      params = {}
    elif method == "catalog.container":
      params = {
        'containerID': kwargs['id']
      }
    elif not method:
      params = {
        'HLS': '1',
        'platformID': kwargs['fmt_id'],
        'trackID': kwargs['id']
      }
    params['orgn'] = "nndesktop"
    params['callback'] = "angular.callbacks._0"
    if method:
      params['method'] = method

    r = self.session.get(self.base + epoint, params=params)
    if method == "user.site.login":
      if "USER_NOT_FOUND" in r.text:
        raise AuthenticationError('Invalid credentials.')
    r.raise_for_status()
    return self.fix_json(r.text)

  def auth(self, email, pwd):
    return self.api_call('secureapi.aspx?', 'user.site.login', email=email, pwd=pwd)

  def get_sub_info(self):
    r = self.api_call('secureapi.aspx?', 'user.site.getSubscriberInfo')
    if not r['Response']['subscriptionInfo']['planName']:
      raise IneligibleError("Free accounts are not eligible to download tracks.")
    return r['Response']['subscriptionInfo']['planName'][9:]

  def get_track_url(self, id, fmt_id):
    r = self.api_call('bigriver/subplayer.aspx?', None,
                      id=id, fmt_id=fmt_id)['streamLink']
    if fmt_id == 4:
      if not "mqa24/" in r:
        self.get_track_url(id, 1)
    return r

  def get_album_meta(self, id):
    return self.api_call('api.aspx?', 'catalog.container', id=id)['Response']
