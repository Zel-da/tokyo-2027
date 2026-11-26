"""index.html 안의 데이터 상수(const X={...}; 한 줄 JSON)를 읽고 고쳐서 다시 쓴다.

사용 예:
    from edit_data import Page
    pg = Page("index.html"); D = pg.data("DAYS"); ...; pg.set("DAYS", D); pg.save()
"""
import json, re


class Page:
    def __init__(self, path):
        self.path = path
        self.s = open(path, encoding="utf8").read()

    def _span(self, name):
        m = re.search(r"^const %s=(.*);$" % re.escape(name), self.s, re.M)
        if not m:
            raise KeyError(name)
        return m

    def data(self, name):
        return json.loads(self._span(name).group(1).replace("<\\/", "</"))

    def set(self, name, val):
        m = self._span(name)
        txt = json.dumps(val, ensure_ascii=False).replace("</", "<\\/")
        self.s = self.s[:m.start(1)] + txt + self.s[m.end(1):]

    def save(self):
        open(self.path, "w", encoding="utf8").write(self.s)


def item(day, iid):
    for it in day["items"]:
        if it["id"] == iid:
            return it
    raise KeyError(iid)


def insert_after(day, after_id, new):
    i = [it["id"] for it in day["items"]].index(after_id)
    day["items"].insert(i + 1, new)
