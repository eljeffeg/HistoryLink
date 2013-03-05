#!/usr/bin/env python
#
# Copyright 2012-2013 Jeff Gentes
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

    def process_group(self, family_group):
        family_list = []
        if family_group and "results" in family_group:
            for item in family_group["results"]:
                family = Family("profile", item)
                family_list.append(family)
        elif family_group and "nodes" in family_group:
            family = Family("profile", family_group)
            family_list.append(family)
        else:
            logging.warning("**** No results ****")
            logging.warning(family_group)
        return family_list

    def get_family_group(self, family_root):
        query = "profile/immediate-family"
        ids = ""
        result = []
        while len(family_root) > 0:
            ids += family_root.pop() + ","
        ids = ids[:-1]
        args = {"ids": ids, "fields": "id,name,gender,master_profile"}
        family_group = self.request(query, args)
        if "error" not in family_group:
            result = self.process_group(family_group)
        else:
            if "message" in family_group["error"]:
                if "Invalid access token"  == family_group["error"]["message"]:
                    result = "Invalid access token"
                elif "Access Denied" == family_group["error"]["message"]:
                    newlist = []
                    startlist = ids.split(",")
                    if len(startlist) == 1:
                        relative = self.get_profile(startlist[0])
                        if "public" in relative:
                            if relative["public"] == False:
                                return [Family("profile", relative, "Access Denied")]
                            else:
                                return []
                        else:
                            return []
                    idlist = [startlist[i::2] for i in range(2)]
                    for family_root in idlist:
                        newlist.extend(self.get_family_group(family_root))
                    result = newlist
        return result

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

    def get_master(self, profiles):
        path = ""
        for profile in profiles:
            path += profile + ","
        path = path[:-1]
        args = {"id": path, "fields": "id,name,master_profile"}
        result = self.request("profile", args)
        match = []
        try:
            for item in result:
                for profile in result[item]:
                    if "master_profile" in profile:
                        match.append({"id": profile["id"], "name": profile["name"]})
        except:
            pass
        return match

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
        """Fetches the given path in the Geni API.

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
            response = _parse_json(e.read())
            if "error" in response and "message" in response["error"]:
                message = response["error"]["message"]
                if "Rate limit exceeded." == message:
                    i = 3 #Try it 3 times
                    while message == "Rate limit exceeded." and i > 0:
                        time.sleep(3)
                        i -= 1
                        try:
                            file = urllib2.urlopen("https://www.geni.com/api/" + path + "?" +
                                                   urllib.urlencode(args), post_data)
                            message = "Pass"
                        except:
                            response = _parse_json(e.read())
                            if "error" in response and "message" in response["error"]:
                                message = response["error"]["message"]
                            else:
                                message = "error"
                                logging.warning("***** " + path + "?" + urllib.urlencode(args) + " *****")
                                logging.warning(response)
                            file = None
                elif "Access Denied" == message:
                    file = None
                else:
                    logging.warning("***** " + path + "?" + urllib.urlencode(args) + " *****")
                    logging.warning(response)
                    file = None
            else:
                logging.warning("***** " + path + "?" + urllib.urlencode(args) + " *****")
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
    def __init__(self, focus, response, error=None):
        self.unions = []
        self.family = []
        self.focus = None
        if error:
            profile = None
            name = None
            if "id" in response:
                profile = response["id"]
            if "name" in response:
                name = response["name"]
            if profile:
                relative = Relative(profile, name, "unknown", False, error)
                if relative:
                    self.family.append(relative)
            else:
                logging.warning('No id? ' + response)
        else:
            if "profile" == focus:
                self.focus = response["focus"]["id"]
            else:
                self.focus = focus
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
                    master = False
                    name = None
                    if "master_profile" in response["nodes"][item]:
                        master = True
                    if "name" in response["nodes"][item]:
                        name = response["nodes"][item]["name"]
                    for edge in response["nodes"][item]["edges"]:
                        rel = response["nodes"][item]["edges"][edge]["rel"]
                        relative = self.process_unions(edge, item, rel, gender, name, master)
                        if relative:
                            self.family.append(relative)

    def get_focus(self):
        return self.focus

    def get_profile(self, profile, gen=0):
        relative = None
        name = None
        if "id" in profile:
            name = profile["name"]
            profile = profile["id"]
        for item in self.family:
            if item.get_id() == profile:
                relative = item
                break
        if name:
            relative_profile = {"id": relative.get_id(), "relation": relative.get_rel(gen), "name": name}
        else:
            relative_profile = {"id": relative.get_id(), "relation": relative.get_rel(gen)}
        return relative_profile

    def get_family_all(self):
        relatives = []
        for item in self.family:
            relatives.append(item.get_id())
        return relatives

    def get_family_branch_group(self):
        relatives = []
        for relative in self.family:
            rel = relative.get_rel()
            id = None
            if rel == "parent" or rel == "father" or rel == "mother":
                id = relative.get_id()
            elif rel == "sibling" or rel == "sister" or rel == "brother":
                id = relative.get_id()
            elif relative.get_message():
                id = relative.get_id()
            if id:
                relatives.append(relative)
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

    def process_unions(self, union, profile, rel, gender, name, master=False):
        for item in self.unions:
            if union == item.get_id():
                return item.get_edge(profile, self.focus, rel, gender, name, master)

class Relative(object):
    def __init__(self, id, name, relation, master=False, message=False):
        self.id = id
        self.relation = relation
        self.master = master
        self.name = name
        self.message = message

    def get_id(self):
        return self.id

    def get_name(self):
        return self.name

    def is_master(self):
        return self.master

    def get_message(self):
        return self.message

    def get_rel(self, gen=0):
        if gen == 0:
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
                newrel = "aunt/uncle/grandparent"
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

    def get_edge(self, profile, focus, rel, gender, name, master=False):
        for x in self.edges:
            if focus == x.get_profile() and profile != focus:
                rel2 = x.get_rel()
                if (rel == "partner" and rel2 == "child" and gender == "male"):
                    return Relative(profile, name, "father", master)
                elif (rel == "partner" and rel2 == "child" and gender == "female"):
                    return Relative(profile, name, "mother", master)
                elif (rel == "partner" and rel2 == "child"):
                    return Relative(profile, name, "parent", master)
                elif (rel == "partner" and rel2 == "partner" and gender == "male" and self.status == "spouse"):
                    return Relative(profile, name, "husband", master)
                elif (rel == "partner" and rel2 == "partner" and gender == "female" and self.status == "spouse"):
                    return Relative(profile, name, "wife", master)
                elif (rel == "partner" and rel2 == "partner" and self.status == "spouse"):
                    return Relative(profile, name, "spouse", master)
                elif (rel == "child" and rel2 == "partner" and gender == "male"):
                    return Relative(profile, name, "son", master)
                elif (rel == "child" and rel2 == "partner" and gender == "female"):
                    return Relative(profile, name, "daughter", master)
                elif (rel == "child" and rel2 == "partner"):
                    return Relative(profile, name, "child", master)
                elif (rel == "child" and rel2 == "child" and gender == "male"):
                    return Relative(profile, name, "brother", master)
                elif (rel == "child" and rel2 == "child" and gender == "female"):
                    return Relative(profile, name, "sister", master)
                elif (rel == "child" and rel2 == "child"):
                    return Relative(profile, name, "sibling", master)
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

