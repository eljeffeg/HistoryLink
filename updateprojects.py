#!/usr/bin/env python
#
# Copyright 2012-2013 Jeff Gentes

import urllib2
import settings
import datetime

if datetime.datetime.today().weekday() == 0:
    urllib2.urlopen(settings.app_url + "projectupdate")
