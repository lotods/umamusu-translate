import sys
from os.path import realpath
import sqlite3
from pathlib import Path, PurePath
from importlib import import_module

sys.path.append(realpath("src"))
import common
import helpers
checkPatched = import_module("import").checkPatched


def extract(db: sqlite3.Connection, stmt: str, savePath: Path):
    # In the spirit of the original db patch, we don't modify old files to keep the db order
    savePath = savePath.with_suffix(".json")
    try:
        oldData = common.TranslationFile(savePath)
    except FileNotFoundError:
        print(f"File not found, creating new: {savePath}")
        oldData = None
    newData = dict()
    cur = db.execute(stmt)
    for row in cur:
        val = row[0]
        newData[val] = oldData.textBlocks.get(val, "") if oldData else ""
    if oldData:
        oldData.textBlocks = newData
        oldData.save()
    else:
        o = {'version': 101, 'type': "mdb", 'lineLength': 0, 'text': newData}
        helpers.writeJson(savePath, o)


def parseArgs():
    ap = common.Args("Extracts master.mdb data for translation", defaultArgs=False)
    ap.add_argument("-src", default=common.GAME_MASTER_FILE, help="Path to master.mdb file")
    ap.add_argument("-dst", default="translations/mdb", type=Path, help="Extraction path")
    ap.add_argument("--no-skill-data", action="store_true", help="Skip extracting skill data (requires nodeJS)")
    ap.add_argument("--no-text", action="store_true", help="Skip extracting standard text data")
    ap.add_argument("-f", "--file", help="Extract specific file name (as found in index.json)")
    ap.add_argument("--forced", action="store_true", help="Ignore mdb patch state")
    return ap.parse_args()

class MdbIndex:
    def __init__(self, idxPath: str):
        self.idx = helpers.readJson(idxPath)
    def parseListSQL(self, l: list):
        base = list()
        complex = list()
        for x in l:
            if isinstance(x, int):
                base.append(str(x))
            else:
                complex.append(self.parseValueSQL(x))
        complex = f" OR {' OR '.join(complex)}" if complex else ""
        return f"{self.spec} IN ({','.join(base)}){complex}"
    def parseDictSQL(self, d: dict):
        sqlText = d.get('sql')
        val = self.parseValueSQL(d['spec'])
        return f"({val} AND {sqlText})" if sqlText else val
    def parseValueSQL(self, val):
        if isinstance(val, list):
            return self.parseListSQL(val)
        elif isinstance(val, dict):
            return self.parseDictSQL(val)
        else:
            return f"{self.spec} = {val}"
    def parseSQL(self, fnFilter = None):
        '''Translates index file to programmatic extraction info.'''
        for entry in self.idx:
            stmt = f"SELECT DISTINCT {entry['field']} FROM {entry['table']}"
            outPathRel = entry['table'] if entry.get("subdir") else ""
            self.spec = entry.get("specifier")
            if self.spec:
                for filename, val in entry['files'].items():
                    if val is None or (fnFilter and filename != fnFilter): continue
                    yield stmt + f" WHERE {self.parseValueSQL(val)};", PurePath(outPathRel, filename)
            else:
                if fnFilter and entry['file'] != fnFilter: continue
                yield stmt+";", PurePath(outPathRel, entry['file'])


def main():
    args = parseArgs()
    if not args.forced and checkPatched(args.src):
        print("master.mdb is patched, aborting extract.")
        return
    if not args.no_text:
        print("Extracting standard text...")
        with sqlite3.connect(args.src) as db:
            for stmt, outPathRel in MdbIndex("src/mdb/index.json").parseSQL(args.file):
                extract(db, stmt, args.dst / outPathRel)
        db.close()
    if not args.no_skill_data:
        print("Extracting skill data...")
        # This is just a QoL thing
        from subprocess import run
        run(["node", "src/scripts/extract-skill-data.js", args.src], check=True)
        import textprocess
        textprocess.processFiles(common.Args.fake(src="translations/mdb/alt/skill-desc.json", lineLength=-1, targetLines=99, forceResize=True))


if __name__ == '__main__':
    main()
