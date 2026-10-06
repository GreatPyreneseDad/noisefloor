def process(records):
    out = []
    for r in records:
        if r:
            if "v" in r:
                if r["v"] is not None:
                    if r["v"] > 0:
                        out.append(r["v"] * 2)
                    else:
                        out.append(0)
                else:
                    out.append(0)
            else:
                out.append(0)
        else:
            out.append(0)
    return out
