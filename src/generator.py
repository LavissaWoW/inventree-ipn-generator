"""Does this need to be here maybe?"""

from plugin import InvenTreePlugin
from plugin.mixins import EventMixin, SettingsMixin
from part.models import Part

import logging
import re

# translation
from django.utils.translation import ugettext_lazy as _

logger = logging.getLogger('inventree')

class AutoGenIPNPlugin(EventMixin, SettingsMixin, InvenTreePlugin):
    """Plugin to generate IPN automatically"""

    AUTHOR = 'Nichlas Walsøe'
    DESCRIPTION = 'Plugin for automatically assigning IPN to parts created with empty IPN fields.'
    VERSION = '0.1'

    NAME = "IPNGenerator"
    SLUG = "ipngen"
    TITLE = "IPN Generator"

    SETTINGS = {
        'ACTIVE': {
            'name': _('Active'), 
            'description': _('IPN generator is active'),
            'validator': bool,
            'default': True
        },
        'ON_CREATE': {
            'name': _('On Create'),
            'description': _('Active when creating new parts'),
            'validator': bool,
            'default': True
        },
       'ON_CHANGE': {
            'name': _('On Edit'),
            'description': _('Active when editing existing parts'),
            'validator': bool,
            'default': True
        },
        'PATTERN': {
            'name': _('IPN pattern'),
            'description': _('Pattern for IPN generation'),
            'default': ''
        },
    }

    min_pattern_char = ord('A')
    max_pattern_char = ord('Z')
    skip_chars = range(ord('['), ord('a'))

    def wants_process_event(self, event):

        if not self.get_setting('ACTIVE'):
            return False

        return event in ['part_part.saved', 'part_part.created']

    def process_event(self, event, *args, **kwargs):
        id = kwargs.pop('id', None)
        model = kwargs.pop('model', None)

        if model != "Part":
            return

        part = Part.objects.get(id=id)
        if part.IPN:
            return

        expression = self.construct_regex()

        latest = Part.objects.filter(IPN__regex=expression).order_by('-IPN').first()

        if not latest:
            part.IPN = self.construct_first_ipn()
        else:
            part.IPN = self.increment_ipn(expression, latest.IPN)
        
        part.save()

        return


    def construct_regex(self):
       
        regex = '^'

        m = re.findall(r"(\{\d+\+?\})|(\([^\d\(\)]+\))|(\[(?:\w+|\w-\w)+\])", self.get_setting('PATTERN'))

        for idx, group in enumerate(m):
            numeric, literal, character = group
            # Numeric, increment
            if numeric:
                start = "+" in numeric
                r = ''
                g = numeric.strip("{}+")
                if start: 
                    regex += f'(?P<Ni{idx}>'
                    for char in g:
                        regex += f'[{char}-9]'
                else:
                    regex += f'(?P<N{g}i{idx}>'
                    regex += f'\d{ {int(g)} }'
                regex += ')'
            
            # Literal, won't change
            if literal:
                l = literal.strip("()")
                regex += f'(?P<Li{idx}>{re.escape(l)})'

            # Letters, a collection or sequence
            # Sequences incremented using ASCII
            if character:
                regex += f'(?P<C'

                sequences = re.findall(r'(\w)(?!-)|(\w\-\w)', character)

                exp = []
                for seq in sequences:
                    single, range = seq

                    if single:
                        exp.append(single)
                    elif range:
                        exp.append(range)
                    
    
                regex += f'{"_".join(exp).replace("-", "")}i{idx}>'
                regex += f'[{"".join(exp)}]'
                regex += ')'

        regex += '$'

        return regex

    def increment_ipn(self, exp, latest):

        m: re.Match = re.match(exp, latest)

        ipn_list = []

        # True after a fields has been incremented
        # Does not apply on count rollover (i.e. 999 -> 001)
        incremented = False

        for key, val in reversed(m.groupdict().items()):

            type, idx = key.split('i')

            if incremented or type == 'L':
                ipn_list.append(val)
                continue

            if type == 'N':
                ipn_list.append(str(int(val)+1))
                incremented = True
            elif type.startswith('C'):
                integerized_char = ord(val)
                choices = type[1:].split("_")

                ranges = any(len(x) > 1 for x in choices)

                if not ranges:
                    if choices.index(val) == len(choices) - 1:
                        ipn_list.append(choices[0])
                    else: 
                        ipn_list.append(choices[choices.index(val) + 1])
                        incremented = True
                else:
                    for choice in choices:
                        if len(choice) > 1:
                            min = ord(choice[0])
                            max = ord(choice[1])
                            if integerized_char in range(min, max + 1):
                                if integerized_char == max -1:
                                    ipn_list.append(choice[0])
                                else:
                                    ipn_list.append(chr(integerized_char + 1))
                                incremented = True
                                break
                        elif choices.index(val) < choices.index(choice):
                            ipn_list.append(choice)
                            incremented = True
                            break

            elif type.startswith('N'):
                num = int(type[1:])
                if len(str(int(val) + 1)) > num:
                    ipn_list.append(str(1).zfill(num))
                else:
                    ipn_list.append(str(int(val)+1).zfill(num))
                    incremented = True

        ipn_list.reverse()
        return "".join(ipn_list)



    def construct_first_ipn(self):

        m = re.findall(r"(\{\d+\+?\})|(\([^\d\(\)]+\))|(\[(?:\w+|(?:\w-\w)+)\])", self.get_setting('PATTERN'))

        ipn = ''

        for group in m:
            numeric, literal, character = group

            if numeric:
                num = numeric.strip("{}+")
                if "+" in numeric: 
                    ipn += num
                else:
                    ipn += str(1).zfill(int(num))

            if literal:
                ipn += literal.strip("()")

            if character:
                ipn += character[0]

        return ipn






