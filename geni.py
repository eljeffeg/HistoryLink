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

import urllib
import urllib2
import logging
import time

# Find a JSON parser
try:
    import simplejson as json
except ImportError:
    try:
        from django.utils import simplejson as json
    except ImportError:
        import json
_parse_json = json.loads

# Find a query string parser
try:
    from urlparse import parse_qs
except ImportError:
    from cgi import parse_qs


class GeniAPI(object):

    def __init__(self, access_token=None):
        self.access_token = access_token

    # based on: http://code.activestate.com/recipes/146306/
    def _encode_multipart_form(self, fields):
        """Fields are a dict of form name-> value
        For files, value should be a file object.
        Other file-like objects might work and a fake name will be chosen.
        Return (content_type, body) ready for httplib.HTTP instance
        """
        BOUNDARY = '----------ThIs_Is_tHe_bouNdaRY_$'
        CRLF = '\r\n'
        L = []
        for (key, value) in fields.items():
            logging.debug("Encoding %s, (%s)%s" % (key, type(value), value))
            if not value:
                continue
            L.append('--' + BOUNDARY)
            if hasattr(value, 'read') and callable(value.read):
                filename = getattr(value, 'name', '%s.jpg' % key)
                L.append(('Content-Disposition: form-data;'
                          'name="%s";'
                          'filename="%s"') % (key, filename))
                L.append('Content-Type: image/jpeg')
                value = value.read()
                logging.debug(type(value))
            else:
                L.append('Content-Disposition: form-data; name="%s"' % key)
            L.append('')
            if isinstance(value, unicode):
                logging.debug("Convert to ascii")
                value = value.encode('ascii')
            L.append(value)
        L.append('--' + BOUNDARY + '--')
        L.append('')
        body = CRLF.join(L)
        content_type = 'multipart/form-data; boundary=%s' % BOUNDARY
        return content_type, body

    def get_family(self, profile=None):
        if not profile:
            profile = "profile"
        elif not str(profile).startswith("profile"):
            profile = "profile-" + profile
        family = Family(profile, self.request(profile + "/immediate-family"))
        #family.print_family()
        return family

    def get_parents(self, profile):
        family = self.get_family(profile)
        return family.get_parents()

    def get_children(self, profile):
        family = self.get_family(profile)
        return family.get_children()

    def get_spouse(self, profile):
        family = self.get_family(profile)
        return family.get_spouse()

    def get_siblings(self, profile):
        family = self.get_family(profile)
        return family.get_siblings()

    def get_project(self, project, path=None, args=None):
        if not str(project).startswith("project"):
            project = "project-" + project
        if path:
            project += "/" + path
        return self.request(project, args)

    def get_profile(self, profile, path=None, args=None):
        if not str(profile).startswith("profile"):
            profile = "profile-" + profile
        if path:
            profile += "/" + path
        return self.request(profile, args)

    def get_project_name(self, project):
        args = {'fields': 'name'}
        name = self.get_project(project, None, args)
        if "name" in name:
            return name["name"]
        return name

    def get_profile_name(self, profile):
        args = {'fields': 'name'}
        name = self.get_profile(profile, None, args)
        if "name" in name:
            return name["name"]
        return name

    def get_profile_info(self, profile):
        args = {'fields': 'name,id'}
        info = self.get_profile(profile, None, args)
        return info

    def get_project_profiles(self, project):
        args = {'fields': 'id,name'}
        proj = Project(project, self.get_project(project, "profiles", args))
        return proj.get_results()

    def get_project_collaborators(self, project):
        args = {'fields': 'id'}
        proj = Project(project, self.get_project(project, "collaborators", args))
        return proj.get_results()

    def get_project_followers(self, project):
        args = {'fields': 'id'}
        proj = Project(project, self.get_project(project, "followers", args))
        return proj.get_results()

    def request(self, path, args=None, post_args=None):
        """Fetches the given path in the Graph API.

        We translate args to a valid query string. If post_args is given,
        we send a POST request to the given path with the given arguments.
        """
        args = args or {}
        response = ""
        if self.access_token:
            if post_args is not None:
                post_args["access_token"] = self.access_token
            else:
                args["access_token"] = self.access_token
        post_data = None if post_args is None else urllib.urlencode(post_args)
        try:
            file = urllib2.urlopen("https://www.geni.com/api/" + path + "?" +
                                   urllib.urlencode(args), post_data)
        except urllib2.HTTPError, e:
            time.sleep(3)
            try:
                file = urllib2.urlopen("https://www.geni.com/api/" + path + "?" +
                                       urllib.urlencode(args), post_data)
            except urllib2.HTTPError, e:
                response = _parse_json(e.read())
                logging.warning("***** " + path + " *****")
                logging.warning(response)
                file = None

        try:
            if file:
                fileInfo = file.info()
                if fileInfo.maintype == 'text':
                    response = _parse_json(file.read())
                elif fileInfo.maintype == 'application':
                    response = _parse_json(file.read())
                elif fileInfo.maintype == 'image':
                    mimetype = fileInfo['content-type']
                    response = {
                        "data": file.read(),
                        "mime-type": mimetype,
                        "url": file.url,
                        }
                else:
                    logging.warning('Maintype was not text or image')
        finally:
            if file:
                file.close()
        return response

class Project(object):
    def __init__(self, focus, response):
        self.focus = focus
        self.response = response
        self.profiles = []
        next = "start"
        while next:
            next = self.process_response()

    def get_json(self):
        return self.response

    def get_results(self):
        return self.profiles

    def process_response(self):
        next = None
        for item in self.response:
            if (item == 'next_page'):
                next = self.response[item]
            if (item == 'results'):
                for xitem in self.response[item]:
                    name = "(No Name)"
                    if "name" in xitem:
                        name = xitem["name"]
                    self.profiles.append({"id": xitem["id"], "name":name })
        if next:
            file = urllib2.urlopen(next)
            self.response = _parse_json(file.read())
        return next


class Family(object):
    def __init__(self, focus, response):
        self.focus = focus
        self.response = response
        self.unions = []
        self.family = []
        if not "nodes" in response:
            return
        for item in response["nodes"]:
            if (str(item).startswith("union")):
                union = Union(str(item), response["nodes"][item])
                if union:
                    self.unions.append(union)

        for item in response["nodes"]:
            if (str(item).startswith("profile")):
                if "gender" in response["nodes"][item]:
                    gender = response["nodes"][item]["gender"]
                else:
                    gender = "Unknown"
                for edge in response["nodes"][item]["edges"]:
                    rel = response["nodes"][item]["edges"][edge]["rel"]
                    relative = self.process_unions(edge, item, rel, gender)
                    if relative:
                        self.family.append(relative)

    def get_json(self):
        return self.response

    def get_profile(self, profile, gen=0):
        relative = None
        for item in self.family:
            if item.get_id() == profile:
                relative = item
                break
        relative_profile = {"id": relative.get_id(), "relation": relative.get_rel(gen)}
        return relative_profile

    def get_family_all(self):
        relatives = []
        for item in self.family:
            relatives.append(item.get_id())
        return relatives

    def get_family_branch(self):
        relatives = []
        for item in self.family:
            rel = item.get_rel()
            if rel == "parent" or rel == "father" or rel == "mother":
                relatives.append(item.get_id())
            elif rel == "sibling" or rel == "aunt" or rel == "uncle":
                relatives.append(item.get_id())
        return relatives

    def get_parents(self):
        relatives = []
        for item in self.family:
            rel = item.get_rel()
            if rel == "father" or rel == "mother" or rel == "parent":
                relatives.append(item.get_id())
        return relatives

    def get_siblings(self):
        relatives = []
        for item in self.family:
            rel = item.get_rel()
            if rel == "brother" or rel == "sister" or rel == "sibling":
                relatives.append(item.get_id())
        return relatives

    def get_children(self):
        relatives = []
        for item in self.family:
            rel = item.get_rel()
            if rel == "son" or rel == "daughter" or rel == "child":
                relatives.append(item.get_id())
        return relatives

    def get_spouse(self):
        relatives = []
        for item in self.family:
            rel = item.get_rel()
            if rel == "wife" or rel == "husband" or rel == "spouse":
                relatives.append(item.get_id())
        return relatives

    def print_family(self):
        print "\nFocus: " + self.focus
        for relative in self.family:
            print  "\t" + relative.get_id() + ", " + relative.get_rel()
        print "\n"

    def process_unions(self, union, profile, rel, gender):
        for item in self.unions:
            if union == item.get_id():
                return item.get_edge(profile, self.focus, rel, gender)

class Relative(object):
    def __init__(self, id, relation):
        self.id = id
        self.relation = relation

    def get_id(self):
        return self.id

    def get_rel(self, gen=None):
        if not gen or gen == 0:
            return self.relation
        else:
            #todo likely needs some work on half siblings, step parents, gen 1, etc.
            newrel = self.relation
            if self.relation == "sister":
                newrel = "aunt"
            elif self.relation == "brother":
                newrel = "uncle"
            elif self.relation == "sibling":
                newrel = "aunt/uncle"
            elif self.relation == "father":
                newrel = "grandfather"
            elif self.relation == "mother":
                newrel = "grandmother"
            elif self.relation == "wife":
                newrel = "spouse"
            elif self.relation == "husband":
                newrel = "spouse"
            elif self.relation == "spouse":
                newrel = "spouse"
            else:
                newrel = "child"
        prefix = ""
        gen -= 1
        if gen > 0:
            prefix = "great "
        if gen > 1:
            if gen == 2:
                prefix = "2nd " + prefix
            elif gen == 3:
                prefix = "3rd " + prefix
            elif gen > 3:
                if gen < 21:
                    prefix = str(gen) + "th " + prefix
                elif gen % 10 == 1:
                    prefix = str(gen) + "st " + prefix
                elif gen % 10 == 2:
                    prefix = str(gen) + "nd " + prefix
                elif gen % 10 == 3:
                    prefix = str(gen) + "rd " + prefix
                else:
                    prefix = str(gen) + "th " + prefix
        return prefix + newrel


class Union(object):
    def __init__(self, id, response):
        self.id = id
        self.edges = []
        self.status = ""
        if "status" in response:
            self.status = response["status"]
        if "edges" in response:
            for item in response["edges"]:
                edge = Edge(item, response["edges"][item]["rel"])
                if edge:
                    self.edges.append(edge)

    def print_union(self):
        print self.id + " (" + self.status + ")"
        for edge in self.edges:
            print "\t" + edge.profile + " (" + edge.rel + ")"

    def get_edge(self, profile, focus, rel, gender):
        for x in self.edges:
            if focus == x.get_profile() and profile != focus:
                rel2 = x.get_rel()
                if (rel == "partner" and rel2 == "child" and gender == "male"):
                    return Relative(profile, "father")
                elif (rel == "partner" and rel2 == "child" and gender == "female"):
                    return Relative(profile, "mother")
                elif (rel == "partner" and rel2 == "child"):
                    return Relative(profile, "parent")
                elif (rel == "partner" and rel2 == "partner" and gender == "male" and self.status == "spouse"):
                    return Relative(profile, "husband")
                elif (rel == "partner" and rel2 == "partner" and gender == "female" and self.status == "spouse"):
                    return Relative(profile, "wife")
                elif (rel == "partner" and rel2 == "partner" and self.status == "spouse"):
                    return Relative(profile, "spouse")
                elif (rel == "child" and rel2 == "partner" and gender == "male"):
                    return Relative(profile, "son")
                elif (rel == "child" and rel2 == "partner" and gender == "female"):
                    return Relative(profile, "daughter")
                elif (rel == "child" and rel2 == "partner"):
                    return Relative(profile, "child")
                elif (rel == "child" and rel2 == "child" and gender == "male"):
                    return Relative(profile, "brother")
                elif (rel == "child" and rel2 == "child" and gender == "female"):
                    return Relative(profile, "sister")
                elif (rel == "child" and rel2 == "child"):
                    return Relative(profile, "sibling")
                else:
                    return None

    def get_id(self):
        return self.id

class Edge(object):
    def __init__(self, profile, rel):
        self.profile = profile
        self.rel = rel

    def get_profile(self):
        return self.profile

    def get_rel(self):
        return self.rel


class GeniAPIError(Exception):
    def __init__(self, result):
        #Exception.__init__(self, message)
        #self.type = type
        self.result = result
        try:
            self.type = result["error_code"]
        except:
            self.type = ""

        # OAuth 2.0 Draft 10
        try:
            self.message = result["error_description"]
        except:
            # OAuth 2.0 Draft 00
            try:
                self.message = result["error"]["message"]
            except:
                # REST server style
                try:
                    self.message = result["error_msg"]
                except:
                    self.message = result

        Exception.__init__(self, self.message)

