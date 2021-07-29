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
        return "%02d:%05.2f" % (min, sec)
    else:
        return "%02d:%02d:%05.2f" % (hour, min, sec)

def get_cd(online):
    return 2.5*(math.sqrt(online+11.96))+6.5

def get_cds(online):

    cd = 2.5*(math.sqrt(online+11.96))+6.5
    cds = []
    total = 0
    for i in range(0, 6):
        t = cd_2(i,cd)
        cds.append(t)
        total+=t
    return cds

if __name__ == "__main__":
    print(get_cds(1))