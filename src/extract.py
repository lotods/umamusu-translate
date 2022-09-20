from pathlib import Path, PurePath
import sqlite3
import csv
from typing import Optional, Union

from Levenshtein import ratio as similarity

import common
from common import GAME_META_FILE, GAME_ASSET_ROOT, TranslationFile, GameBundle

def queryfyStoryid(group, id, idx):
    group = group or "__"
    id = id or "____"
    idx = idx or "___"
    return group, id, idx

def queryDB(db=None, storyId=None):
    if storyId:
        group, id, idx = queryfyStoryid(*common.parseStoryId(args.type, storyId))
    else:
        group, id, idx = queryfyStoryid(args.group, args.id, args.idx)

    if args.type == "story":
        pattern = f"{args.type}/data/{group}/{id}/{args.type}timeline%{idx}"
    elif args.type == "home":
        pattern = f"{args.type}/data/00000/{group}/{args.type}timeline_00000_{group}_{id}{idx}%"
    elif args.type == "race":
        pattern = f"{args.type}/storyrace/text/storyrace_{group}{id}{idx}%"
    elif args.type == "lyrics":
        if args.idx and not args.id: id = args.idx
        pattern = f"live/musicscores/m{id}/m{id}_lyrics"
    elif args.type == "preview":
        if args.idx and not args.id: id = args.idx
        pattern = f"outgame/announceevent/loguiasset/ast_announce_event_log_ui_asset_0{id}"

    externalDb = bool(db)
    if not externalDb:
        db = sqlite3.connect(GAME_META_FILE)
    cur = db.execute(f"SELECT h, n FROM a WHERE n LIKE '{pattern}';")
    results = cur.fetchall()
    if not externalDb:
        db.close()

    return results


def extractAsset(asset: GameBundle, storyId, tlFile=None) -> Union[None, TranslationFile]:
    asset.readPatchState()
    if asset.isPatched: return

    asset.load()

    if not asset.rootAsset.serialized_type.nodes:
        return

    tree = asset.rootAsset.read_typetree()
    export = {
        'bundle': asset.bundleName,
        'type': args.type,
        'storyId': "",
        'title': "",
        'text': list()
    }
    transferExisting = DataTransfer(tlFile)

    if args.type == "race":
        export['storyId'] = tree['m_Name'][-9:]

        for block in tree['textData']:
            textData = extractText("race", block)
            transferExisting(storyId, textData)
            export['text'].append(textData)
    elif args.type == "lyrics":
        # data = index.read()
        # export['storyId'] = data.name[1:5]
        # export['text'] = extractText("lyrics", data.text)
        export['storyId'] = tree['m_Name'][1:5]

        r = csv.reader(tree['m_Script'].splitlines(), skipinitialspace=True)
        header = True
        # intern-kun can't help goof up even csv
        for row in r:
            if header: header = False; continue
            textData = extractText("lyrics", row)
            transferExisting(storyId, textData)
            export['text'].append(textData)
    elif args.type == "preview":
        export['storyId'] = tree['m_Name'][-4:]
        for block in tree['DataArray']:
            textData = extractText("preview", block)
            transferExisting(storyId, textData)
            export['text'].append(textData)
    else:
        export['storyId'] = "".join(storyId) if args.type == "home" else tree['StoryId']
        export['title'] = tree['Title']

        for block in tree['BlockList']:
            for clip in block['TextTrack']['ClipList']:
                pathId = clip['m_PathID']
                textData = extractText(args.type, asset.assets[pathId])
                if not textData:
                    continue

                if "origClipLength" in textData:
                    if args.verbose: print(f"Attempting anim data export at BlockIndex {block['BlockIndex']}")
                    clipsToUpdate = list()
                    for trackGroup in block['CharacterTrackList']:
                        for key in trackGroup.keys():
                            if key.endswith("MotionTrackData") and trackGroup[key]['ClipList']:
                                clipsToUpdate.append(trackGroup[key]['ClipList'][-1]['m_PathID'])
                    if clipsToUpdate:
                        textData['animData'] = list()
                        for clipPathId in clipsToUpdate:
                            animAsset = asset.assets[clipPathId]
                            if animAsset:
                                animData = animAsset.read_typetree()
                                animGroupData = dict()
                                animGroupData['origLen'] = animData['ClipLength']
                                animGroupData['pathId'] = clipPathId
                                textData['animData'].append(animGroupData)
                            elif args.verbose:
                                print(f"Couldn't find anim asset ({clipPathId}) at BlockIndex {block['BlockIndex']}")
                    elif args.verbose:
                        print(f"Anim clip list empty at BlockIndex {block['BlockIndex']}")

                textData['pathId'] = pathId  # important for re-importing
                textData['blockIdx'] = block['BlockIndex']  # to help translators look for specific routes
                transferExisting(storyId, textData)
                export['text'].append(textData)

    if not export['text']: return # skip empty text assets
    export = common.TranslationFile.fromData(export)
    if transferExisting.file:
        export.snapshot(copyFrom=transferExisting.file)
    return export


def extractText(assetType, obj):
    if assetType == "race":
        # obj is already read
        o = {
            'jpText': obj['text'],
            'enText': "",
            'blockIdx': obj['key']
        }
    elif assetType == "lyrics":
        time, text, *_ = obj
        o = {
            'jpText': text,
            'enText': "",
            'time': time
        }
        return o
    elif assetType == "preview":
        o = {
                'jpName': obj['Name'],
                'enName': "",
                'jpText': obj['Text'],
                'enText': "",
            }
    elif obj.serialized_type.nodes:
        tree = obj.read_typetree()
        o = {
            'jpName': tree['Name'],
            'enName': "",  # todo: auto lookup
            'jpText': tree['Text'],
            'enText': "",
            'nextBlock': tree['NextBlock'],  # maybe for adding blocks to split dialogue later
        }
        # home has no auto mode so adjustments aren't needed
        if assetType == "story":
            o['origClipLength'] = tree['ClipLength']
        choices = tree['ChoiceDataList']  # always present
        if choices:
            o['choices'] = list()
            for c in choices:
                o['choices'].append({
                    'jpText': c['Text'],
                    'enText': "",
                    'nextBlock': c['NextBlock']
                })

        textColor = tree['ColorTextInfoList']  # always present
        if textColor:
            o['coloredText'] = list()
            for c in textColor:
                o['coloredText'].append({
                    'jpText': c['Text'],
                    'enText': ""
                })
    return o if o['jpText'] else None


class DataTransfer:
    def __init__(self, file: common.TranslationFile = None):
        self.file = file
        self.offset = 0
        self.simRatio = 0.9 if args.update and args.type != "lyrics" else 0.99
        self.printed = False

    def filePrint(self, text):
        if not self.printed:
            print(f"\nIn {self.file.name}:")
            self.printed = True
        print(text)

    def __call__(self, storyId, textData):
        # Existing files are skipped before reaching here so there's no point in checking when we know the result already.
        # Only continue when forced to.
        if not args.overwrite or self.file == 0:
            return
        group, id, idx = storyId

        if self.file is None:
            file = next((Path(args.dst) / group / id).glob(f"{idx}*.json"), None)
            if file is None:  # Check we actually found a file above
                self.file = 0
                return

            self.file = common.TranslationFile(file)

        textSearch = False
        targetBlock = None
        textBlocks = self.file.textBlocks
        txtIdx = 0
        if 'blockIdx' in textData:
            txtIdx = max(textData["blockIdx"] - 1 - self.offset, 0)
            if txtIdx < len(textBlocks):
                targetBlock = textBlocks[txtIdx]
                if not args.upgrade and similarity(targetBlock['jpText'], textData['jpText']) < self.simRatio:
                    self.filePrint(f"jpText does not match at bIdx {textData['blockIdx']}")
                    targetBlock = None
                    textSearch = True
            else:
                textSearch = True
        else:
            # TODO: The below code is completely broken
            # self.filePrint(f"No block idx at {txtIdx}")
            # txtIdx = int(txtIdx)
            textSearch = True

        if textSearch:
            self.filePrint("Searching by text")
            for i, block in enumerate(textBlocks):
                if similarity(block['jpText'], textData['jpText']) > self.simRatio:
                    self.filePrint(f"Found text at block {i}")
                    self.offset = txtIdx - i
                    targetBlock = block
                    break
            if not targetBlock:
                self.filePrint("Text not found")

        if targetBlock:
            if args.upgrade:
                textData['jpText'] = targetBlock['jpText']
            textData['enText'] = targetBlock['enText']
            if 'enName' in targetBlock:
                if args.upgrade:
                    textData['jpName'] = targetBlock['jpName']
                textData['enName'] = targetBlock['enName']
            if 'choices' in targetBlock:
                for txtIdx, choice in enumerate(textData['choices']):
                    try:
                        if args.upgrade:
                            choice['jpText'] = targetBlock['choices'][txtIdx]['jpText']
                        choice['enText'] = targetBlock['choices'][txtIdx]['enText']
                    except IndexError:
                        self.filePrint(f"New choice at bIdx {targetBlock['blockIdx']}.")
                    except KeyError:
                        self.filePrint(f"Choice mismatch when attempting data transfer at {txtIdx}")
            if 'coloredText' in targetBlock:
                for txtIdx, cText in enumerate(textData['coloredText']):
                    if args.upgrade:
                        cText['jpText'] = targetBlock['coloredText'][txtIdx]['jpText']
                    cText['enText'] = targetBlock['coloredText'][txtIdx]['enText']
            if 'skip' in targetBlock:
                textData['skip'] = targetBlock['skip']
            if 'newClipLength' in targetBlock:
                textData['newClipLength'] = targetBlock['newClipLength']
            if args.upgrade and self.file.version > 4:
                textData['origClipLength'] = targetBlock['origClipLength']
                for i, group in enumerate(textData.get("animData", [])):
                    group['origLen'] = targetBlock['animData'][i]['origLen']


def exportAsset(bundle: Optional[str], path: str, db=None):
    if bundle is None:  # update mode
        assert db is not None
        tlFile = common.TranslationFile(path)
        if args.upgrade and tlFile.version == common.TranslationFile.latestVersion:
            print(f"File already on latest version, skipping: {path}")
            return

        storyId = tlFile.getStoryId()
        try:
            bundle, _ = queryDB(db, storyId)[0]
        except IndexError:
            print(f"Error looking up {storyId}. Corrupt data or removed asset?")
            return
        if bundle == tlFile.bundle:
            if args.verbose:
                print(f"Bundle {bundle} not changed, skipping.")
            return
        else:
            print(f"Updating {bundle}")
    else:  # make sure tlFile is set for the call later
        tlFile = None

    if args.update:
        group, id, idx = common.parseStoryId(args.type, storyId)
    else:
        group, id, idx = common.parseStoryIdFromPath(args.type, path)

    exportDir = Path(args.dst) if args.type in ("lyrics", "preview") else Path(args.dst) / group / id

    # Skip if already exported and we're not overwriting
    if not args.overwrite:
        file = next(exportDir.glob(f"{idx}*.json"), None)
        if file is not None:
            if args.verbose:
                print(f"Skipping existing: {file.name}")
            return

    asset = GameBundle.fromName(bundle, load=False)
    if not asset.exists:
        print(f"AssetBundle {bundle} does not exist in your game data, skipping...")
        return
    try:
        outFile = extractAsset(asset, (group, id, idx), tlFile)
        if not outFile:
            return
    except:
        print(f"Failed extracting bundle {bundle}, g {group}, id {id} idx {idx} to {exportDir}")
        raise

    # Remove invalid path chars (win)
    delSet = {34, 42, 47, 58, 60, 62, 63, 92, 124}
    title = ""
    for c in outFile.data['title']:
        cp = ord(c)
        if cp > 31 and cp not in delSet:
            title += c
    idxString = f"{idx} ({title})" if title else idx

    outFile.setFile(str(exportDir / f"{idxString}.json"))
    outFile.save()


def parseArgs():
    global args
    ap = common.Args("Extract Game Assets to Translation Files")
    ap.add_argument("-dst")
    ap.add_argument("-O", "--overwrite", action="store_true", help="Overwrite existing Translation Files")
    ap.add_argument("-upd", "--update", nargs="*", choices=common.TARGET_TYPES,
                    help="Re-extract existing files, optionally limited to given type.\nImplies -O, ignores -dst and -t")
    ap.add_argument("-upg", "--upgrade", action="store_true",
                    help="Attempt tlfile version upgrade with minimal extraction.\nCan be used on patched files. Implies -O")
    ap.add_argument("-v", "--verbose", action="store_true", help="Print extra info")
    args = ap.parse_args()

    if args.dst is None:
        args.dst = PurePath("translations") / args.type
    if args.upgrade or args.update is not None:
        args.overwrite = True
    if isinstance(args.update, list) and len(args.update) == 0:
        args.update = common.TARGET_TYPES


def main():
    parseArgs()
    if args.update is not None:
        print("Updating exports, this could take a while...")
        db = sqlite3.connect(GAME_META_FILE)
        try:
            # check if a type was specifically given and use that if so, otherwise use all
            for type in args.update or common.TARGET_TYPES:
                args.dst = PurePath("translations") / type
                args.type = type
                files = common.searchFiles(type, args.group, args.id, args.idx, changed=args.changed)
                print(f"Found {len(files)} files for {type}.")
                for i, file in enumerate(files):
                    try:
                        exportAsset(None, file, db)
                    except:
                        print(f"Failed in file {i} of {type}: {file}")
                        raise  # TODO consider continuing
        finally:
            db.close()
    else:
        print(f"Extracting group {args.group}, id {args.id}, idx {args.idx} (overwrite: {args.overwrite})\n"
              f"from {GAME_ASSET_ROOT} to {args.dst}")
        q = queryDB()
        print(f"Found {len(q)} files.")
        for bundle, path in q:
            exportAsset(bundle, path)
    print("Processing finished successfully.")


if __name__ == '__main__':
    main()
