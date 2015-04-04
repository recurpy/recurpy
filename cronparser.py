from collections import defaultdict
from datetime import *
import re


#TODO: refactor ruleset, string parser into own classes
#TODO: rename moy -> month
#TODO: option to set min/max year


class InvalidFieldError(Exception):
    pass


class CronParser(object):
    """
        Space delimited cron string:
        
        minute[0..59] hour[0..23] dom[1..31] moy[1..12] dow[1..7](1=Monday) year

        allows "*", "-", "/", and "[0-9]"
    """
    fields = ["minute", "hour", "dom", "moy", "dow", "year"]
    holiday_re = "[\*]\s[\*]\s(\d{1,2})\s(\d{1,2})\s[\*]\s(\d{4})"

    def __init__(self, rules=list(), exceptions=list(), in_utc=False):
        """
            rules and exeptions should look like:
            [("name", "* * * * * *"), ...]
        """
        
        self.rules = defaultdict(list)
        self.exceptions = defaultdict(list)
        self.holiday_exceptions = {}  #Optimization to reduce the effect of one day exceptions on the runtime
                                      #  Looks like {(dd,mm,yyyy): name}  

        for rname, rule in rules:
            self.rules[rname].append(self.parse(rule))

        for ename, exception in exceptions:
            #Holidays can be queried faster than more general rules
            if self.is_holiday(exception):
                self.holiday_exceptions[self.holiday_tuple(exception)] = ename
            else:
                self.exceptions[ename].append(self.parse(exception))



    def diff_rules(self, r1, r2):
        """
            remove r2 from r1 (difference)

            Can handle an empty dictionary as a ruleset
        """
        return {f: r1.get(f, set()) - r2.get(f, set()) for f in CronParser.fields}
                


    def parse_field(self, f, minimum=0, maximum=0):
        """
            Returns a set containing the right elements
            minimum and maximum define the range of values used for wildcards
            minimum and maximum as passed should be inclusive integers. 
            All +1s will be added here.
                e.g. 0,1 -> set([0,1])

        """
        digits = {i for i in xrange(10)}

        final_range = []
        try:
            #Handle clauses containing '/'
            divisor = 1
            div_splits = f.split("/")

            if len(div_splits) > 1 and div_splits[1].isdigit():
                divisor = int(div_splits[1])

            # *, */x
            if f[0] == "*":
                return set(xrange(minimum, maximum + 1, divisor))
               
            # Don't parse the divisor again 
            f = div_splits[0]

            # i, j-k, j-k/x
            hyphen_splits = f.split("-")
            
            if hyphen_splits[0].isdigit():
                #j-k, j-k/x
                if len(hyphen_splits) > 1:
                    return set( xrange(int(hyphen_splits[0]), int(hyphen_splits[1]) + 1, divisor) )

                # i
                return {int(f)}

            #If no rule matches, the string isn't valid
            raise InvalidFieldError(f)

        #Saves boilerplate checking length of string,
        # Intead, assume it's valid, and otherwise throw error
        except IndexError:
            raise InvalidFieldError(f)


    
    def parse(self, cron_string):
        """
            Parses a cron_string that looks like "m h dom moy dow year"
            return is a dictionary of sets holding integers contained by that field
        """
        fields = cron_string.split(" ")
        return {
            "minutes": self.parse_field(fields[0], 0, 59),
            "hours": self.parse_field(fields[1], 0, 23),
            "dom": self.parse_field(fields[2], 1, 31),
            "moy": self.parse_field(fields[3], 1, 12),
            "dow": self.parse_field(fields[4], 1, 7),
            "year": self.parse_field(fields[5], 2000, 2025)  #What is a sensible year here?  EOT?
        }
    

    def is_holiday(self, rule):
        """
            Holiday is defined as one day, one month, one year:

            e.g. Easter: "* * 5 4 * 2015"
        """
        return re.compile(CronParser.holiday_re).match(rule.strip()) is not None


    def holiday_tuple(self, hrule):
        """
            assumes hrule is a holiday
            returns tuple: (dd, mm, yyyy)
        """
        return tuple([ int(d) for d in re.findall(CronParser.holiday_re, hrule.strip())[0] ])


    def check_ruleset(self, ruleset, time_obj):
        """
            Returns True/False if time_obj is contained in ruleset
        """

        #If all checks pass, the time_obj belongs to this ruleset
        #Reverse order to ensure holidays are fast
        if time_obj.year not in ruleset["year"]:
            return False
        
        if time_obj.month not in ruleset["moy"]:
            return False

        if time_obj.day not in ruleset["dom"]:
            return False
        
        if time_obj.isoweekday() not in ruleset["dow"]:
            return False

        if time_obj.hour not in ruleset["hours"]:
            return False

        if time_obj.minute not in ruleset["minutes"]:
            return False



        return True


    def pick_rules(self, time_obj):
        """
            Picks the rules that time_obj belongs to.  
            
            time_obj is a datetime object.

            if self.in_utc is defined, then the time_obj will be converted to UTC

            If rules overlap, the time_obj will belong to multiple rules.
            Therefore return is a list:
                e.g.
                [], ["2001"], ["weekday_afternoons", "every_thursday"],
        """
        

        rule_list = []

        #Check holiday exceptions:
        holiday_exc_name = self.holiday_exceptions.get((time_obj.day, time_obj.month, time_obj.year), None)

        if holiday_exc_name is not None:
            return [holiday_exc_name]

        #Check exceptions
        for ename, exceptions in self.exceptions.items():
            for exception in exceptions:
                if self.check_ruleset(exception, time_obj):
                    return [ename]

        #No exceptions match, so all rules are available
        for rname, rulesets in self.rules.items():
            for ruleset in rulesets:
                if self.check_ruleset(ruleset, time_obj):
                    rule_list.append(rname)

        return rule_list


