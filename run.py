#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import time
import json
import feedgenerator
import requests
from urlparse import urlparse, parse_qs

url = 'https://api.allegro.pl/offers/listing'
auth_url = 'https://allegro.pl/auth/oauth'

scriptdir = os.path.dirname(os.path.realpath(__file__))
authfile = os.path.join(scriptdir, 'auth.json')
with open(os.path.join(scriptdir, 'config.json')) as f:
    config = json.load(f)

user = config['restID']
password = config['restSecret']
outdir = config['outputDir']
redirectURI = config['restRedirectURI']

session = requests.Session()
session.auth=(user, password)

class AuthException(Exception):
    def __init__(self, response):
        super(AuthException, self).__init__('auth error')
        self.data = response

def save_auth(data):
    old_mask = os.umask(0o077)
    with open(authfile, 'w') as f:
        json.dump(data, f)
    os.umask(old_mask)

def refresh_auth(auth_data, redirect_uri):
    r = session.post(url=auth_url+'/token',
            data={'grant_type': 'refresh_token',
                  'refresh_token': auth_data['refresh_token'],
                  'redirect_uri': redirect_uri})
    new_data = r.json()
    if r.status_code == 200:
        save_auth(new_data)
    else:
        raise AuthException(new_data)
    return new_data

# manual auth (first time and/or every 356days and/or when token expires)
def sign_in(client_id, redirect_uri):
    print 'open this address in browser:'
    print '   %s/authorize?response_type=code&client_id=%s&redirect_uri=%s' % (auth_url, client_id, redirect_uri)
    print 'copy the redirected url and paste it here (you have 10sec):'
    code_uri = raw_input()
    code = parse_qs(urlparse(code_uri).query)['code'][0]
    print 'access code: %s' % code
    r = session.post(url=auth_url+'/token',
            data={'grant_type': 'authorization_code',
                  'code': code,
                  'redirect_uri': redirect_uri})
    auth_data = r.json()
    save_auth(auth_data)
    return auth_data

# try loading and refreshing old auth
auth_data = {}
try:
    with open(authfile, 'r') as f:
        auth_data = json.load(f)
    auth_data = refresh_auth(auth_data, redirectURI)
except AuthException, e:
    print 'allegro auth failed, remove auth.json and run manually to renew auth'
    print e.data
    sys.exit()
except:
    print 'manual auth needed'
    auth_data = sign_in(user, redirectURI)

# switch to OAuth and set accept headers
session.auth=None
session.headers.update({
    'Authorization': '%s %s' % ('Bearer', auth_data['access_token']),
    'Accept': 'application/vnd.allegro.public.v1+json'}
)

range_filters = ['price']
filter_map = {
    'userId': 'seller.id',
    'search': 'phrase',
    'category': 'category.id',
    'price': 'price',
}

def make_price_line(item):
    ret = []
    if item['sellingMode']['format'] == 'BUY_NOW':
        ret.append(u"Cena Kup Teraz: %s zł" % item['sellingMode']['price']['amount'])
    if item['sellingMode']['format'] == 'AUCTION':
            ret.append(u"Aktualna cena: %s zł" % item['sellingMode']['price']['amount'])
    return '<br/>'.join(ret)

def make_date_line(item):
    suffix = ''
    if 'publication' in item:
        suffix = " (%s)" % item['publication']['endingAt'] # ??? 2018-06-21 19:51:14
#    return item.timeToEnd + suffix
    return suffix

def make_image_line(item):
    for img in item['images']:
         return "<img style='width:200px' src='%s'/>" % img['url']
    return ''

def make_rss(name, query, scope):
    filter_query={'fallback': False}
    for k,v in query.iteritems():
        if k not in filter_map:
            continue
        if k in range_filters:
            if 'min' in v:
                filter_query[filter_map[k]+'.from'] = v['min']
            if 'max' in v:
                filter_query[filter_map[k]+'.to'] = v['max']
        else:
            filter_query[filter_map[k]] = v

    if scope=='descriptions':
        filter_query['searchMode'] = 'DESCRIPTIONS'

    res = session.get(url, params=filter_query)
    data = res.json()

    feed = feedgenerator.Rss201rev2Feed(title='Allegro - %s' % query.get('search', name), link='http://allegro.pl', description=name, language='pl')

    items = data['items']['regular']

    for item in items:
        feed.add_item(
            title=item['name'],
            link="https://allegro.pl/show_item.php?item=%s" % item['id'],
            description=u"Sprzedający: <a href='https://allegro.pl/show_user.php?uid=%s'>%s</a><br/>%s<br/>Do końca: %s<br/>%s" % (
                item['seller']['id'], item['seller']['id'],
                make_price_line(item),
                make_date_line(item),
                make_image_line(item),
            )
        )
    with open(os.path.join(outdir, 'allegro-' + name + '.xml'), 'w') as f:
        feed.write(f, 'utf-8')

feedsdir = os.path.join(scriptdir, 'feeds')
for fname in os.listdir(feedsdir):
    if not fname.endswith('.json'):
        continue
    with open(os.path.join(feedsdir, fname)) as f:
        data = json.load(f)
        make_rss(data['name'], data['query'], data.get('scope', 'titles'))
