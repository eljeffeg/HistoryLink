#!/usr/bin/env python
#
# Copyright 2012 Jeff Gentes
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

#Python client library for the Geni Platform.

import base64
import functools
import json
import hashlib
import hmac
import time
import logging
import os
import httplib #for custom error handler
import threading
import tornado.database
import tornado.escape
import tornado.httpclient
import tornado.ioloop
import tornado.web
#import tornado.wsgi
import urllib
import urllib2
import urlparse
from tornado.options import define, options
from tornado import gen
from tornado.web import asynchronous

import geni

# Find a JSON parser
try:
    import simplejson as json
except ImportError:
    try:
        from django.utils import simplejson as json
    except ImportError:
        import json
_parse_json = json.loads

define("compiled_css_url")
define("compiled_jquery_url")
define("config")
define("cookie_secret")
define("debug", type=bool, default=True)
define("mysql_host")
define("mysql_database")
define("mysql_user")
define("mysql_password")
define("geni_app_id")
define("geni_app_secret")
define("geni_canvas_id")
define("geni_namespace")
define("app_url")
define("listenport", type=int)
define("silent", type=bool)
define("historyprofiles", type=set)

#class GeniApplication(tornado.wsgi.WSGIApplication):
class GeniApplication(tornado.web.Application):
    def __init__(self):
        self.linkHolder = LinkHolder()
        base_dir = os.path.dirname(__file__)
        settings = {
            "cookie_secret": options.cookie_secret,
            "static_path": os.path.join(base_dir, "static"),
            "template_path": os.path.join(base_dir, "templates"),
            "debug": options.debug,
            "geni_canvas_id": options.geni_canvas_id,
            "app_url": options.app_url,
            "ui_modules": {
                "TimeConvert": TimeConvert,
                "SHAHash": SHAHash,
                },
            }
        #tornado.wsgi.WSGIApplication.__init__(self, [
        tornado.web.Application.__init__(self, [
            tornado.web.url(r"/", HomeHandler, name="home"),
            tornado.web.url(r"/projects", ProjectHandler, name="logout"),
            tornado.web.url(r"/history", HistoryHandler, name="history"),
            tornado.web.url(r"/historylist", HistoryList),
            tornado.web.url(r"/historycount", HistoryCount),
            tornado.web.url(r"/historyprocess", HistoryProcess),
            tornado.web.url(r"/projectupdate", ProjectUpdate),
            tornado.web.url(r"/projectsubmit", ProjectSubmit),
            tornado.web.url(r"/projectlist", ProjectList),
            tornado.web.url(r"/login", LoginHandler, name="login"),
            tornado.web.url(r"/logout", LogoutHandler, name="logout"),
            tornado.web.url(r"/geni", GeniCanvasHandler),
            ], **settings)

class ErrorHandler(tornado.web.RequestHandler):
    """Generates an error response with status_code for all requests."""
    def __init__(self, application, request, status_code):
        tornado.web.RequestHandler.__init__(self, application, request)
        self.set_status(status_code)

    def get_error_html(self, status_code, **kwargs):
        self.require_setting("static_path")
        if status_code in [404, 500, 503, 403]:
            filename = os.path.join(self.settings['static_path'], '%d.html' % status_code)
            if os.path.exists(filename):
                f = open(filename, 'r')
                data = f.read()
                f.close()
                return data
        return "<html><title>%(code)d: %(message)s</title>"\
               "<body class='bodyErrorPage'>%(code)d: %(message)s</body></html>" % {
                   "code": status_code,
                   "message": httplib.responses[status_code],
                   }

    def prepare(self):
        raise tornado.web.HTTPError(self._status_code)

## override the tornado.web.ErrorHandler with our default ErrorHandler
tornado.web.ErrorHandler = ErrorHandler

class LinkHolder(object):
    cookie = {}

    def set(self, id, key, value):
        if not id in self.cookie:
            self.cookie[id] = {}
        self.cookie[id][key] = value

    def add_matches(self, id, profile):
        if not id in self.cookie:
            self.cookie[id] = {}
        if not "matches" in self.cookie[id]:
            self.cookie[id]["matches"] = []
        exists = None
        if "hits" in self.cookie[id]:
            self.cookie[id]["hits"] += 1
        else:
            self.cookie[id]["hits"] = 1
        for items in self.cookie[id]["matches"]:
            if items["id"] == profile["id"]:
                #Give more weight to parents over aunts/uncles
                exists = True
                if profile["message"]:
                    pass
                elif "aunt" in profile["relation"]:
                    pass
                elif "uncle" in profile["relation"]:
                    pass
                elif "mother" in items["relation"]:
                    pass
                elif "father" in items["relation"]:
                    pass
                else:
                    items["relation"] = profile["relation"]
        if not exists:
            self.cookie[id]["matches"].append(profile)
        return exists

    def get_matches(self, id):
        if not id in self.cookie:
            return []
        if not "matches" in self.cookie[id]:
            return []
        return self.cookie[id]["matches"]

    def get_matchcount(self, id):
        if not id in self.cookie:
            return 0
        if not "matches" in self.cookie[id]:
            return 0
        return len(self.cookie[id]["matches"])


    def add_history(self, id, history):
        if not id in self.cookie:
            self.cookie[id] = {}
        if not "history" in self.cookie[id]:
            self.cookie[id]["history"] = set(history)
        else:
            self.cookie[id]["history"].update(history)

    def get_history(self, id):
        if not id in self.cookie:
            return set([])
        if not "history" in self.cookie[id]:
            return set([])
        return self.cookie[id]["history"]

    def clear_matches(self, id):
        if not id in self.cookie:
            return
            #if "matches" in self.cookie[id]:
            #self.cookie[id]["matches"] = []
        if "hits" in self.cookie[id]:
            self.cookie[id]["hits"] = 0
        return

    def get(self, id, key):
        if id in self.cookie:

            if key in self.cookie[id]:
                return self.cookie[id][key]
        if key == "count":
            return 0
        elif key == "stage":
            return "parents"
        elif key == "running":
            return 0
        elif key == "hits":
            return 0
        else:
            return None

    def stop(self, id):
        if id and id in self.cookie:
            del self.cookie[id]

class BaseHandler(tornado.web.RequestHandler):
    @property
    def backend(self):
        return Backend.instance()

    def prepare(self):
        self.set_header('P3P', 'CP="HONK"')

    def write_error(self, status_code, **kwargs):
        import traceback
        if self.settings.get("debug") and "exc_info" in kwargs:
            exc_info = kwargs["exc_info"]
            trace_info = ''.join(["%s<br/>" % line for line in traceback.format_exception(*exc_info)])
            request_info = ''.join(["<strong>%s</strong>: %s<br/>" % (k, self.request.__dict__[k] ) for k in self.request.__dict__.keys()])
            error = exc_info[1]
            self.set_header('Content-Type', 'text/html')
            self.finish("""<html>
                             <title>%s</title>
                             <body>
                                <h2>Error</h2>
                                <p>%s</p>
                                <h2>Traceback</h2>
                                <p>%s</p>
                                <h2>Request Info</h2>
                                <p>%s</p>
                             </body>
                           </html>""" % (error, error,
                                         trace_info, request_info))

    def get_current_user(self):
        if not self.get_secure_cookie("uid"):
            return None
        user = {'id': self.get_secure_cookie("uid"), 'access_token': self.get_secure_cookie("access_token"), 'name': self.get_secure_cookie("name")}
        return user


    def login(self, next):
        if not self.current_user:
            logging.info("Need user grant permission, redirect to oauth dialog.")
            oauth_url = self.get_login_url(next)
            logging.info(oauth_url)
            self.render("oauth.html", oauth_url=oauth_url)
        else:
            return

    def get_login_url(self, next=None):
        if not next:
            next = self.request.full_url()
        if not next.startswith("http://") and not next.startswith("https://") and\
           not next.startswith("http%3A%2F%2F") and not next.startswith("https%3A%2F%2F"):
            next = urlparse.urljoin(self.request.full_url(), next)
        code = self.get_argument("code", None)
        if code:
            return self.request.protocol + "://" + self.request.host +\
                   self.reverse_url("login") + "?" + urllib.urlencode({
                "next": next,
                "code": code,
                })
        redirect_uri = self.request.protocol + "://" + self.request.host +\
                       self.reverse_url("login") + "?" + urllib.urlencode({"next": next})
        loginurl = "https://www.geni.com/platform/oauth/authorize?" + urllib.urlencode({
            "client_id": options.geni_app_id,
            "redirect_uri": redirect_uri,
            })
        return loginurl

    def write_json(self, obj):
        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.finish(json.dumps(obj))

    def render(self, template, **kwargs):
        kwargs["error_message"] = self.get_secure_cookie("message")
        if kwargs["error_message"]:
            kwargs["error_message"] = base64.b64decode(kwargs["error_message"])
            self.clear_cookie("message")
        tornado.web.RequestHandler.render(self, template, **kwargs)

    def set_error_message(self, message):
        self.set_secure_cookie("message", base64.b64encode(message))

class HomeHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        self.render("home.html")

class ProjectUpdate(BaseHandler):
    @tornado.web.asynchronous
    @tornado.web.authenticated
    def get(self):
        self.write("update initiated")
        self.finish()
        user = self.current_user
        projects = self.backend.get_projectlist()
        for item in projects:
            print "Updating Project: " + item["name"]
            self.backend.add_project(str(item["id"]), user)
        options.historyprofiles = set(self.backend.get_history_profiles())

class ProjectSubmit(BaseHandler):
    @tornado.web.asynchronous
    @tornado.web.authenticated
    def post(self):
        project = self.get_argument("project", None)
        user = self.current_user
        logging.info(" *** " +  str(user["name"]) + " (" + str(user["id"]) + ") submitted project " + project)
        if not project:
            self.finish()
        args = {"user": user, "base": self, "project": project}
        ProjectWorker(self.worker_done, args).start()

    def worker_done(self, value):
        try:
            self.finish(value)
        except:
            return

class ProjectWorker(threading.Thread):
    user = None
    base = None
    project = None
    def __init__(self, callback=None, *args, **kwargs):
        self.user = args[0]["user"]
        self.base = args[0]["base"]
        self.project = args[0]["project"]
        args = {}
        super(ProjectWorker, self).__init__(*args, **kwargs)
        self.callback = callback

    def run(self):
        self.base.backend.add_project(self.project, self.user)
        options.historyprofiles = set(self.base.backend.get_history_profiles())
        self.callback('DONE')

class ProjectHandler(BaseHandler):
    @tornado.web.authenticated
    @tornado.web.asynchronous
    def get(self):
        projects = self.backend.query_projects()
        try:
            self.render("projects.html", projects=projects)
        except:
            return

class ProjectList(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        projects = self.backend.query_projects()
        count = self.backend.get_profile_count()
        try:
            self.render("projectlist.html", projects=projects, count=count)
        except:
            return

class HistoryHandler(BaseHandler):
    @tornado.web.authenticated
    @tornado.web.asynchronous
    def get(self):
        user = self.current_user
        profile_id = self.get_argument("profile", None)
        if profile_id:
            info = self.backend.get_profile_info(profile_id, user)
            username = info["name"]
            userid = info["id"]
        else:
            username = user["name"]
            userid = user["id"]
        self.render("history.html", username=username, userid=userid)

class HistoryList(BaseHandler):
    @tornado.web.authenticated
    @tornado.web.asynchronous
    def get(self):
        user = self.current_user
        cookie = self.application.linkHolder
        matches = cookie.get_matches(user["id"])
        profile = self.get_argument("profile", None)
        hits = cookie.get(user["id"], "hits")
        showmatch = len(matches) - hits
        who = "is your"
        if profile != user["id"]:
            who = None
        i = 1
        for item in matches:
            if item["message"]:
                if (i > showmatch):
                    try:
                        logging.info(" *** " + str(item["message"]) + " Match for " +  str(user["name"]) + " on " + item["id"] + ": " + item["name"])
                    except:
                        pass
            else:
                if (i > showmatch):
                    try:
                        logging.info(" *** Project Match for " +  str(user["name"]) + " on " + item["id"] + ": " + item["name"])
                    except:
                        pass
            i += 1
        cookie.clear_matches(user["id"])
        self.render("historylist.html", matches=matches, who=who)

class HistoryCount(BaseHandler):
    @tornado.web.authenticated
    @tornado.web.asynchronous
    def get(self):
        user = self.current_user
        cookie = self.application.linkHolder
        result = self.get_argument("status", None)
        count = cookie.get(user["id"], "count")
        stage = cookie.get(user["id"], "stage")
        status = cookie.get(user["id"], "running")
        hits = cookie.get(user["id"], "hits")
        match = cookie.get_matchcount(user["id"])
        try:
            logging.info("  * " + str(user["name"]) + " (" + str(user["id"]) + "), count: " + str(count) + ", stage: " + str(stage))
        except:
            pass
        if result and result == "stop":
            status = 0
            self.application.linkHolder.stop(user["id"])
        elif result and result == "start":
            status = 1
            cookie.set(user["id"], "running", 1)
            cookie.set(user["id"], "count", 0)
            cookie.set(user["id"], "stage", "parents")
            cookie.set(user["id"], "hits", 0)
            count = 0
            stage = "parents"
        self.set_header("Cache-control", "no-cache")
        self.render("historycount.html", count=count, status=status, stage=stage, hits=hits, match=match)

    def post(self):
        user = self.current_user
        self.application.linkHolder.stop(user["id"])
        try:
            self.finsih()
        except:
            return

class HistoryProcess(BaseHandler):
    @tornado.web.authenticated
    @tornado.web.asynchronous
    def get(self):
        profile = self.get_argument("profile", None)
        master = self.get_argument("master", None)
        project = self.get_argument("project", True)
        problem = self.get_argument("problem", None)
        limit = self.get_argument("limit", None)
        if master == "false":
            master = None
        if problem == "false":
            problem = None
        if project == "false":
            project = None
        user = self.current_user
        self.application.linkHolder.set(user["id"], "count", 0)
        self.application.linkHolder.set(user["id"], "running", 1)
        self.application.linkHolder.set(user["id"], "stage", "parents")
        if not options.historyprofiles:
            options.historyprofiles = set(self.backend.get_history_profiles())
        if not profile:
            profile = user["id"]
        args = {"user": user, "base": self, "profile": profile, "master": master, "project": project, "problem": problem, "limit": limit}
        HistoryWorker(self.worker_done, args).start()

    def worker_done(self, value):
        try:
            self.finish(value)
        except:
            return

class HistoryWorker(threading.Thread):
    user = None
    base = None
    rootprofile = None
    master = None
    problem = None
    project = None
    limit = None
    cookie = None
    family_root = []
    def __init__(self, callback=None, *args, **kwargs):
        self.user = args[0]["user"]
        self.base = args[0]["base"]
        self.rootprofile = args[0]["profile"]
        self.master = args[0]["master"]
        self.project = args[0]["project"]
        self.problem = args[0]["problem"]
        self.limit = args[0]["limit"]
        self.cookie = self.base.application.linkHolder
        args = {}
        super(HistoryWorker, self).__init__(*args, **kwargs)
        self.callback = callback

    def run(self):
        profile = self.user["id"]
        rootprofile = self.rootprofile
        if not rootprofile:
            rootprofile = profile
        self.family_root.append(rootprofile)
        gen = 0
        self.setGeneration(gen)
        while len(self.family_root) > 0:
            root = []
            root.extend(self.family_root)
            self.family_root = []
            if not self.limit or int(self.limit) >= gen:
                self.threadme(root, gen, 3, 10)
                gen += 1
                self.setGeneration(gen)
        self.cookie.set(profile, "running", 0)
        self.callback('DONE')



    def checkdone(self):
        if (self.cookie.get(self.user["id"], "running") == 0):
            return True
        else:
            return False

    def setGeneration(self, gen):
        stage = None
        if gen == 0:
            stage = "parents"
        elif gen == 1:
            stage = "grand parents"
        elif gen == 2:
            stage = "great grandparents"
        elif gen > 2:
            stage = self.genPrefix(gen) + " great grandparents"
        self.cookie.set(self.user["id"], "stage", stage)
        return

    def genPrefix(self, gen):
        gen -= 1
        value = ""
        if gen == 2:
            value = str(gen) + "nd"
        elif gen == 3:
            value = str(gen) + "rd"
        elif gen > 3:
            if gen < 21:
                value =  str(gen) + "th"
            elif gen % 10 == 1:
                value = str(gen) + "st"
            elif gen % 10 == 2:
                value = str(gen) + "nd"
            elif gen % 10 == 3:
                value = str(gen) + "rd"
            else:
                value = str(gen) + "th"
        return value

    def checkmatch(self, family):
        match = []
        for item in family:
            if item in options.historyprofiles:
                match.append(item)
        return match

    def threadme(self, family_root, gen, threadlimit=None, idlimit=10, timeout=0.05):
        assert threadlimit > 0, "need at least one thread";
        printlock = threading.Lock()
        threadpool = []

        # keep going while work to do or being done
        while family_root or threadpool:
            done = self.checkdone()
            if done:
                break
            parent_list = []
            # while there's room, remove source files
            # and add to the pool
            while family_root and (threadlimit is None or len(threadpool) < threadlimit):
                i = idlimit
                sub_root = []
                while i > 0:
                    sub_root.append(family_root.pop())
                    if len(family_root) > 0:
                        i -= 1
                    else:
                        i = 0
                wrkr = SubWorker(self, sub_root, gen, printlock)
                wrkr.start()
                threadpool.append(wrkr)

            # remove completed threads from the pool
            for thr in threadpool:
                thr.join(timeout=timeout)
                if not thr.is_alive():
                    threadpool.remove(thr)
        #print("all threads are done")

class SubWorker(threading.Thread):
    def __init__(self, root, family_list, gen, printlock,**kwargs):
        super(SubWorker,self).__init__(**kwargs)
        self.family_list = family_list
        self.root = root
        self.gen = gen
        self.lock = printlock # so threads don't step on each other's prints

    def run(self):
        #with self.lock:
        profile = self.root.user["id"]
        the_group = self.root.base.backend.get_family_group(self.family_list, self.root.user)
        if the_group:
            for this_family in the_group:
                rematch = None
                done = self.root.checkdone()
                if done:
                    break
                relatives = this_family.get_family_branch_group()
                for relative in relatives:
                    if self.root.project and relative.get_id() in options.historyprofiles:
                        with self.lock:
                            projects = self.root.base.backend.get_projects(relative.get_id())
                        match = {"id": relative.get_id(), "relation": relative.get_rel(self.gen), "name": relative.get_name(), "message": False, "projects": projects}
                        rematch = self.root.cookie.add_matches(profile, match)
                    elif self.root.master and relative.is_master():
                        projects = [None]
                        match = {"id": relative.get_id(), "relation": relative.get_rel(self.gen), "name": relative.get_name(), "message": "Master Profile", "projects": projects}
                        rematch = self.root.cookie.add_matches(profile, match)
                    elif self.root.problem and relative.get_message():
                        projects = [None]
                        match = {"id": relative.get_id(), "relation": relative.get_rel(self.gen), "name": relative.get_name(), "message": relative.get_message(), "projects": projects}
                        self.root.cookie.add_matches(profile, match)
                        rematch = True
                count = int(self.root.cookie.get(profile, "count")) + len(relatives)
                self.root.cookie.set(profile, "count", count)
                parents = this_family.get_parents()
                history =  self.root.cookie.get_history(profile)
                for parent in parents:
                    if not rematch and parent not in history:
                        self.root.family_root.append(parent)
            self.root.cookie.add_history(profile, self.root.family_root)

class LoginHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        next = self.get_argument("next", None)
        code = self.get_argument("code", None)
        if not next:
            self.redirect(self.get_login_url(self.reverse_url("home")))
            return
        if not next.startswith("https://" + self.request.host + "/") and\
           not next.startswith("http://" + self.request.host + "/") and\
           not next.startswith("http%3A%2F%2F" + self.request.host + "/") and\
           not next.startswith("https%3A%2F%2F" + self.request.host + "/") and\
           not next.startswith(self.settings.get("geni_canvas_id")) and\
           not next.endswith(options.geni_app_id):
            raise tornado.web.HTTPError(
                404, "Login redirect (%s) spans hosts", next)
        if self.get_argument("error", None):
            logging.warning("Geni login error: %r", self.request.arguments)
            self.set_error_message(
                "An Login error occured with Geni. Please try again later.")
            self.redirect(self.reverse_url("home"))
            return
        if not code:
            self.redirect(self.get_login_url(next))
            return

        redirect_uri = self.request.protocol + "://" + self.request.host +\
                       self.request.path + "?" + urllib.urlencode({"next": next})
        url = "https://www.geni.com/platform/oauth/request_token?" +\
              urllib.urlencode({
                  "client_id": options.geni_app_id,
                  "client_secret": options.geni_app_secret,
                  "redirect_uri": redirect_uri,
                  "code": code,
                  })
        client = tornado.httpclient.AsyncHTTPClient()
        client.fetch(url, self.on_access_token)

    def on_access_token(self, response):
        if response.error:
            self.set_error_message(
                "An error occured with Geni. Possible Issue: Third Party Cookies disabled.")
            self.redirect(self.reverse_url("home"))
            return
        mytoken = json.loads(response.body)
        access_token = mytoken["access_token"]
        url = "https://www.geni.com/api/profile?" + urllib.urlencode({
            "access_token": access_token,
            })
        client = tornado.httpclient.AsyncHTTPClient()
        client.fetch(url, functools.partial(self.on_profile, access_token))

    def on_profile(self, access_token, response):
        if response.error:
            self.set_error_message(
                "A profile response error occured with Geni. Please try again later.")
            self.redirect(self.reverse_url("home"))
            return
        profile = json.loads(response.body)
        self.set_secure_cookie("uid", profile["id"])
        self.set_secure_cookie("name", profile["name"])
        self.set_secure_cookie("access_token", access_token)
        self.redirect(self.get_argument("next", self.reverse_url("home")))
        return

class LogoutHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        self.set_secure_cookie("uid", None)
        redirect_uri = self.request.protocol + "://" + self.request.host
        user = self.current_user
        access_token = user["access_token"]
        urllib2.urlopen("https://www.geni.com/platform/oauth/invalidate_token?" + urllib.urlencode({
            "access_token": access_token
        }))
        self.redirect("http://www.geni.com")

class GeniCanvasHandler(HomeHandler):
    @tornado.web.asynchronous
    def get(self, *args, **kwds):
        logging.info("Geni Canvas called.")
        if not self.current_user:
            self.login(self.settings.get("geni_canvas_id"))
        else:
            super(GeniCanvasHandler, self).get(*args, **kwds)

class Backend(object):
    def __init__(self):
        self.db = tornado.database.Connection(
            host=options.mysql_host, database=options.mysql_database,
            user=options.mysql_user, password=options.mysql_password)

    @classmethod
    def instance(cls):
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance

    def get_family(self, profile, user):
        geni = self.get_API(user)
        return geni.get_family(profile)

    def get_family_group(self, family_root, user):
        geni = self.get_API(user)
        return geni.get_family_group(family_root)

    def get_master(self, profiles, user):
        geni = self.get_API(user)
        return geni.get_master(profiles)

    def add_project(self, project_id, user):
        if not user:
            return
        if not project_id:
            return
        if not project_id.isdigit():
            return
        existing_id = None
        try:
            existing_id = self.db.query("SELECT id FROM projects WHERE id = %s", project_id)
        except:
            #Try to handle error (2006 MySQL server has gone away)
            existing_id = self.db.query("SELECT id FROM projects WHERE id = %s", project_id)
        if not existing_id:
            projectname = self.get_project_name(project_id, user)
            self.db.execute(
                "INSERT IGNORE INTO projects (id, name) "
                "VALUES (%s,%s)", project_id, projectname)
        projectprofiles = self.get_project_profiles(project_id, user)
        if projectprofiles and len(projectprofiles) > 0:
            pass
        else:
            return
        query = ""
        for item in projectprofiles:
            query += '(' + project_id + ',"' + item["id"] + '"),'
        query = "INSERT IGNORE INTO links (project_id,profile_id) VALUES " + query[:-1]
        try:
            self.db.execute(query)
        except:
            self.db.execute(query)
        try:
            profilecount = self.db.query("SELECT COUNT(profile_id) FROM links WHERE project_id = %s", project_id)
        except:
            profilecount = self.db.query("SELECT COUNT(profile_id) FROM links WHERE project_id = %s", project_id)
        if not profilecount:
            return
        if "COUNT(profile_id)" in profilecount[0]:
            self.db.execute("UPDATE projects SET count=%s WHERE id=%s", int(profilecount[0]["COUNT(profile_id)"]), project_id)
        return

    def get_project_profiles(self, project, user):
        geni = self.get_API(user)
        project = geni.get_project_profiles(project)
        return project

    def get_profile_name(self, profile, user):
        geni = self.get_API(user)
        return geni.get_profile_name(profile)

    def get_profile_info(self, profile, user):
        geni = self.get_API(user)
        return geni.get_profile_info(profile)

    def get_project_name(self, project, user):
        geni = self.get_API(user)
        return geni.get_project_name(project)

    def get_geni_request(self, path, user, args=None):
        geni = self.get_API(user)
        return geni.request(str(path), args)

    def get_API(self, user):
        if user:
            cookie = user['access_token']
        else:
            cookie = options.geni_app_id + "|" + options.geni_app_secret
        giniapi = geni.GeniAPI(cookie)
        return giniapi

    def query_projects(self):
        result = None
        try:
            result = self.db.query("SELECT * FROM projects ORDER BY id")
        except:
            result = self.db.query("SELECT * FROM projects ORDER BY id")
        return result

    def get_history_profiles(self):
        try:
            profiles = self.db.query("SELECT DISTINCT profile_id FROM links")
        except:
            profiles = self.db.query("SELECT DISTINCT profile_id FROM links")
        logging.info("Building history profile list.")
        profilelist = []
        for item in profiles:
            profilelist.append(item["profile_id"])
        return profilelist

    def get_projectlist(self):
        try:
            projects = self.db.query("SELECT id,name FROM projects")
        except:
            projects = self.db.query("SELECT id,name FROM projects")
        return projects

    def get_projects(self, id):
        try:
            projects = self.db.query("SELECT links.project_id, projects.name FROM links, projects WHERE links.project_id=projects.id AND links.profile_id = %s", id)
        except:
            projects = self.db.query("SELECT links.project_id, projects.name FROM links, projects WHERE links.project_id=projects.id AND links.profile_id = %s", id)
        projectlist = []
        for item in projects:
            projectlist.append({"id": item["project_id"], "name": item["name"]})
        return projectlist

    def get_profile_count(self):
        profilecount = None
        count = 0
        try:
            profilecount = self.db.query("SELECT DISTINCT COUNT(profile_id) FROM links")
        except:
            profilecount = self.db.query("SELECT DISTINCT COUNT(profile_id) FROM links")
        if profilecount and "COUNT(profile_id)" in profilecount[0]:
            count = "{:,.0f}".format(int(profilecount[0]["COUNT(profile_id)"]))
        return count

class TimeConvert(tornado.web.UIModule):
    def render(self, dt):
        return str(time.mktime(dt.timetuple()))

class SHAHash(tornado.web.UIModule):
    def render(self, shared_private_key, data):
        return hashlib.sha1(repr(data) + "," + shared_private_key).hexdigest()

class ResponseItem(tornado.web.UIModule):
    def render(self, response):
        return response


def load_signed_request(signed_request, app_secret):
    try:
        sig, payload = signed_request.split(u'.', 1)
        sig = base64_url_decode(sig)
        data = json.loads(base64_url_decode(payload))


        expected_sig = hmac.new(app_secret, msg=payload, digestmod=hashlib.sha256).digest()


        if sig == expected_sig and data[u'issued_at'] > (time.time() - 86400):
            return data
        else:
            return None
    except ValueError, ex:
        return None

def base64_url_decode(data):
    data = data.encode(u'ascii')
    data += '=' * (4 - (len(data) % 4))
    return base64.urlsafe_b64decode(data)


def self(args):
    pass


def main():
    tornado.options.parse_command_line()
    options.historyprofiles = None
    if options.config:
        tornado.options.parse_config_file(options.config)
    else:
        path = os.path.join(os.path.dirname(__file__), "settings.py")
        tornado.options.parse_config_file(path)
    from tornado.httpserver import HTTPServer
    from tornado.ioloop import IOLoop
    #from tornado.wsgi import WSGIContainer 
    #http_server = HTTPServer(WSGIContainer(GeniApplication()))
    http_server = HTTPServer(GeniApplication())
    http_server.listen(int(os.environ.get("PORT",8080)))
    IOLoop.instance().start()

if __name__ == "__main__":
    main()
