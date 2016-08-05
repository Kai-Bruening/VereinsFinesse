#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import math

def checkdigit(id_without_check):
    # allowable characters within identifier
    valid_chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVYWXZ_"

    # remove leading or trailing whitespace, convert to uppercase
    id_without_checkdigit = id_without_check.strip().upper()

    # this will be a running total
    sum = 0

    # loop through digits from right to left
    for n, char in enumerate(reversed(id_without_checkdigit)):

        if not valid_chars.count(char):
            raise Exception('InvalidIDException')

        # our "digit" is calculated using ASCII value - 48
        digit = ord(char) - 48

        # weight will be the current digit's contribution to the running total
        weight = None
        if n % 2 == 0:
            # for alternating digits starting with the rightmost, we use our formula this is the same as
            # multiplying x 2 and adding digits together for values 0 to 9.  Using the  following formula allows us
            # to gracefully calculate a weight for non-numeric "digits" as well (from their ASCII value - 48).
            weight = (2 * digit) - (digit / 5) * 9
        else:
            # even-positioned digits just contribute their ascii value minus 48
            weight = digit

        # keep a running total of weights
        sum += weight

    # avoid sum less than 10 (if characters below "0" allowed, this could happen)
    sum = math.fabs(sum) + 10

    # check digit is amount needed to reach next number divisible by ten. Return an integer.
    return int((10 - (sum % 10)) % 10)

def append_checkdigit(id_without_check):
    digit = checkdigit(id_without_check)
    return id_without_check + unicode(digit)

def check_and_strip_checkdigit(id_with_check):
    if len(id_with_check) < 2:
        return None
    ist_digit = id_with_check[len(id_with_check) - 1]
    id_without_check = id_with_check[:len(id_with_check) - 1]
    soll_digit = unicode(checkdigit(id_without_check))
    if soll_digit != ist_digit:
        return None
    return id_without_check

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print "Need a number to calculate a check digit for."
        exit(1)
    text = sys.argv[1]
    result = checkdigit(text)
    print result

