#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import time
import json
import feedgenerator
from suds.client import Client
from suds.sudsobject import asdict, items as suds_items

url = 'https://webapi.allegro.pl/service.php?wsdl'
client = Client(url)

scriptdir = os.path.dirname(os.path.realpath(__file__))
with open(os.path.join(scriptdir, 'config.json')) as f:
    config = json.load(f)

webAPI = config['webAPI']
countryId = config['countryId']
outdir = config['outputDir']

range_filters = ['price']

def make_price_line(item):
    ret = []
    for price in item.priceInfo.item:
        if price.priceType == 'buyNow':
            ret.append(u"Cena Kup Teraz: %.2f zł" % price.priceValue)
        if price.priceType == 'bidding':
            ret.append(u"Aktualna cena: %.2f zł" % price.priceValue)
    return '<br/>'.join(ret)

def make_date_line(item):
    suffix = ''
    if hasattr(item, 'endingTime'):
        suffix = " (%s)" % item.endingTime #2018-06-21 19:51:14
    return item.timeToEnd + suffix

def make_image_line(item):
    if item.photosInfo == '':
        return ''
    for img in item.photosInfo.item:
        if img.photoIsMain and img.photoSize == 'medium':
            return "<img src='%s'/>" % img.photoUrl
    return ''

def make_rss(name, query):
    filter_query=client.factory.create('ArrayOfFilteroptionstype')
    for k,v in query.iteritems():
        filter_options = client.factory.create('FilterOptionsType')
        filter_options.filterId = k

        if k in range_filters:
            filter_range = client.factory.create('RangeValueType')
            if 'min' in v:
                filter_range.rangeValueMin = v['min']
            if 'max' in v:
                filter_range.rangeValueMax = v['max']
            filter_options.filterValueRange = filter_range
        else:
            filter_array = client.factory.create('ArrayOfString')
            filter_array.item = v
            filter_options.filterValueId = filter_array

        filter_query.item.append(filter_options)

    res = client.service.doGetItemsList(webAPI, countryId, filter_query, resultScope=3)

    if res.itemsCount <= 0:
        return

    feed = feedgenerator.Rss201rev2Feed(title='Allegro - %s' % query['search'], link='http://allegro.pl', description=name, language='pl')
    for item in res.itemsList.item:
        feed.add_item(
            title=item.itemTitle,
            link="https://allegro.pl/show_item.php?item=%s" % item.itemId,
            description=u"Sprzedający: <a href='https://allegro.pl/show_user.php?uid=%s'>%s</a><br/>%s<br/>Do końca: %s<br/>%s" % (
                item.sellerInfo.userId, item.sellerInfo.userLogin,
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
        make_rss(data['name'], data['query'])
