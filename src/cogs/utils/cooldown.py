from cogs.utils.scrapping import get_page_source
import requests
import json
import math

def sum_up_to_n(n):
    r = 0
    for i in range(n):
        r += i
    return r

def cd_2(stack,cd):
    stackMultiplier = 3
    if stack == 0:
        return cd
    return (cd * stackMultiplier) * (1 + stack + sum_up_to_n(stack - 1))

def time_convert(seconds):
    min, sec = divmod(seconds, 60)
    hour, min = divmod(min, 60)
    if hour == 0:
        return "%02dm%02ds" % (min, round(sec,2))
    else:
        return "%02dh%02dm%02ds" % (hour, min, round(sec,2))

def get_cds(online):

    cd = 2.5*(math.sqrt(online+12))+6.5
    cds = []
    text= f"Pxls Cooldown for {online} users:\n"
    total = 0
    for i in range(0, 6):
        t = cd_2(i,cd)
        cds.append(t)
        total+=t
        text+=f'\t**{i}/6** => {time_convert(t)} '
        text+= f'(total: {time_convert(total)})\n'
    return cds

if __name__ == "__main__":
    print(get_cds([]))