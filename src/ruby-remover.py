import sqlite3
from types import SimpleNamespace

from common import patch, logger
from common.constants import GAME_META_FILE
from common.types import StoryId, GameBundle


def removeRuby(args, db: sqlite3.Connection):
    storyId = StoryId.queryfy(StoryId(args.type, args.set, args.group, args.id, args.idx))
    del storyId.set
    # del storyId.type

    q = db.execute(f"select h, n from a where n like 'story/data/__/____/ast_ruby_{storyId}'")
    patched = total = 0
    dummytl = SimpleNamespace(data=dict())
    for bundle, path in q:
        bundle = GameBundle.fromName(bundle, load=False)
        if bundle.isPatched:
            logger.info(f"Skipping {StoryId.parseFromPath(storyId.type, path)} ({bundle.bundleName}): Already patched")
        else:
            bundle.load()
            tree = bundle.rootAsset.read_typetree()
            tree["DataArray"] = []
            bundle.rootAsset.save_typetree(tree)
            bundle.markPatched(dummytl)
            bundle.save()
            patched += 1
        total += 1
    return patched, total


def parseArgs(args=None):
    ap = patch.Args("Removes ruby data from assets")
    ap.add_argument("-dst", default=GAME_META_FILE, help="Path to master.mdb file")
    args = ap.parse_args(args)
    args.type = "story"
    return args


def main(args: patch.Args = None):
    args = args or parseArgs(args)
    try:
        with sqlite3.connect(args.dst, isolation_level=None) as db:
            db.execute("PRAGMA journal_mode = MEMORY;")
            p, t = removeRuby(args, db)
            print(f"Processed {p}/{t} files")
    finally:
        db.close()


if __name__ == "__main__":
    main()
