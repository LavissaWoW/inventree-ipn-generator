from plugin import InvenTreePlugin
from plugin.mixins import EventMixin, SettingsMixin
from part.models import Part

from django.core.exceptions import ValidationError

import logging
import re

logger = logging.getLogger("inventree")

PERMITTED_SPECIAL_LITERALS = "\-.:/\\"


def validate_pattern(pattern):
    """Validates pattern groups"""
    regex = re.compile(r"(\{\d+\+?\})|(\[(?!\w\])(?:\w+|(?:\w-\w)+)+\])")
    if not regex.search(pattern):
        raise ValidationError("Pattern must include more than Literals")

    return True


class AutoGenIPNPlugin(EventMixin, SettingsMixin, InvenTreePlugin):
    """Plugin to generate IPN automatically"""

    AUTHOR = "Nichlas W."
    DESCRIPTION = (
        "Plugin for automatically assigning IPN to parts created with empty IPN fields.\
        IPN pattern syntax can be found on the website linked here."
    )
    VERSION = "0.1"
    WEBSITE = "https://github.com/LavissaWoW/inventree-ipn-generator"

    NAME = "IPNGenerator"
    SLUG = "ipngen"
    TITLE = "IPN Generator"

    SETTINGS = {
        "ACTIVE": {
            "name": "Active",
            "description": "IPN generator is active",
            "validator": bool,
            "default": True,
        },
        "ON_CREATE": {
            "name": "On Create",
            "description": "Active when creating new parts",
            "validator": bool,
            "default": True,
        },
        "ON_CHANGE": {
            "name": "On Edit",
            "description": "Active when editing existing parts",
            "validator": bool,
            "default": False,
        },
        "PATTERN": {
            "name": "IPN pattern",
            "description": "Pattern for IPN generation (See website for guide)",
            "default": "(IPN-){4}",
            "validator": validate_pattern,
        },
    }

    min_pattern_char = ord("A")
    max_pattern_char = ord("Z")
    skip_chars = range(ord("["), ord("a"))

    def wants_process_event(self, event):
        """Lets InvenTree know what events to listen for."""

        if not self.get_setting("ACTIVE"):
            return False

        if event == "part_part.saved":
            return self.get_setting("ON_CHANGE")

        if event == "part_part.created":
            return self.get_setting("ON_CREATE")

        return False

    def process_event(self, event, *args, **kwargs):
        """Main plugin handler function"""

        if not self.get_setting("ACTIVE"):
            return False

        id = kwargs.pop("id", None)
        model = kwargs.pop("model", None)

        # Events can fire on unrelated models
        if model != "Part":
            logger.debug("IPN Generator: Event Model is not part")
            return

        # Don't create IPNs for parts with IPNs
        part = Part.objects.get(id=id)
        if part.IPN:
            return

        pattern = self.get_pattern_for_part(part)

        expression = self.construct_regex(pattern, True)
        latest = Part.objects.filter(IPN__regex=expression).order_by("-IPN").first()

        if not latest:
            part.IPN = self.construct_first_ipn(pattern)
        else:
            grouped_expression = self.construct_regex(pattern)
            part.IPN = self.increment_ipn(grouped_expression, latest.IPN)

        part.save()

        return

    def get_pattern_for_part(self, part):
        """Return the pattern for a given part, applying category metadata overrides."""

        pattern = self.get_setting("PATTERN")

        if not part:
            return pattern

        category = getattr(part, "category", None)
        if not category:
            return pattern

        prefix = None

        if hasattr(category, "get_metadata"):
            try:
                prefix = category.get_metadata("prefix", None)
            except TypeError:
                prefix = category.get_metadata("prefix")
            except Exception:  # pragma: no cover - defensive, depends on InvenTree version
                prefix = None
        elif hasattr(category, "metadata"):
            metadata = category.metadata or {}
            prefix = metadata.get("prefix")

        if not prefix:
            return pattern

        allowed = rf"[^0-9A-Za-z{PERMITTED_SPECIAL_LITERALS}]"
        sanitized_prefix = re.sub(allowed, "", str(prefix))

        if not sanitized_prefix:
            return pattern

        return re.sub(r"\([\w\(\)\-.:/\\]+\)", f"({sanitized_prefix})", pattern, count=1)

    def construct_regex(self, pattern=None, disable_groups=False):
        """Constructs a valid regex from provided IPN pattern.
        This regex is used to find the latest assigned IPN
        """
        regex = "^"

        if pattern is None:
            pattern = self.get_setting("PATTERN")

        m = re.findall(
            r"(\{\d+\+?\})|(\([\w\(\)\-.:/\\]+\))|(\[(?:\w+|\w-\w)+\])",
            pattern,
        )

        for idx, group in enumerate(m):
            numeric, literal, character = group
            # Numeric, increment
            if numeric:
                start = "+" in numeric
                g = numeric.strip("{}+")
                if start:
                    regex += "("
                    if not disable_groups:
                        regex += f"?P<Np{g}i{idx}>"
                    for char in g:
                        regex += f"[{char}-9]"
                else:
                    regex += "("
                    if not disable_groups:
                        regex += f"?P<N{g}i{idx}>"
                    regex += f"\d{ {int(g)} }"
                regex += ")"

            # Literal, won't change
            if literal:
                lit = literal.strip("()")
                regex += "("
                if not disable_groups:
                    regex += f"?P<Li{idx}>"
                regex += f"{re.escape(lit)})"

            # Letters, a collection or sequence
            # Sequences incremented using ASCII
            if character:
                regex += "("
                if not disable_groups:
                    regex += "?P<C"

                sequences = re.findall(r"(\w)(?!-)|(\w\-\w)", character)

                exp = []
                for seq in sequences:
                    single, range = seq

                    if single:
                        exp.append(single)
                    elif range:
                        exp.append(range)

                if not disable_groups:
                    regex += f'{"_".join(exp).replace("-", "")}i{idx}>'
                regex += f'[{"".join(exp)}]'
                regex += ")"

        regex += "$"

        return regex

    def increment_ipn(self, exp, latest):
        """Deconstructs IPN pattern based on latest IPN and constructs a the next IPN in the series."""
        m: re.Match = re.match(exp, latest)

        ipn_list = []

        # True after a fields has been incremented
        # Does not apply on count rollover (i.e. 999 -> 001)
        incremented = False

        for key, val in reversed(m.groupdict().items()):
            type, _ = key.split("i")

            if incremented or type == "L":
                ipn_list.append(val)
                continue

            if type == "N":
                ipn_list.append(str(int(val) + 1))
                incremented = True
            elif type.startswith("C"):
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
                                if integerized_char == max:
                                    ipn_list.append(choice[0])
                                else:
                                    ipn_list.append(chr(integerized_char + 1))
                                incremented = True
                                break
                        elif choices.index(val) < choices.index(choice):
                            ipn_list.append(choice)
                            incremented = True
                            break

            elif type.startswith("N"):
                if type[1] == "p":
                    num = int(type[2:])
                else:
                    num = int(type[1:])
                if type[1] == "p":
                    next = int(val) + 1
                    if len(str(next)) > len(type[2:]):
                        ipn_list.append(type[2:])
                    else:
                        ipn_list.append(str(next))
                elif len(str(int(val) + 1)) > num:
                    ipn_list.append(str(1).zfill(num))
                else:
                    ipn_list.append(str(int(val) + 1).zfill(num))
                    incremented = True

        ipn_list.reverse()
        return "".join(ipn_list)

    def construct_first_ipn(self, pattern=None):
        """No IPNs matching the pattern were found. Constructing the first IPN."""

        if pattern is None:
            pattern = self.get_setting("PATTERN")

        m = re.findall(
            r"(\{\d+\+?\})|(\([\w\(\)\-.:/\\]+\))|(\[(?:\w+|(?:\w-\w)+)\])",
            pattern,
        )

        ipn = ""

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
                ipn += character.strip("[]")[0]

        return ipn
