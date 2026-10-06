def m(v):
    s=sorted(v);n=len(s)
    return s[n//2] if n%2 else (s[n//2-1]+s[n//2])/2
