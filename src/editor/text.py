import re
import tkinter as tk
from functools import partial
from tkinter import colorchooser
from typing import Union, TYPE_CHECKING

from . import fonts
from .spellcheck import SpellCheck

if TYPE_CHECKING:
    from common.types import TranslationFile

TkDisplaysText = Union[tk.Text, tk.Entry, tk.Label]


class ColorManager:
    ACTIVE: str = None

    def __init__(self, master: tk.Text) -> None:
        self.colors: set[str] = set()
        self.master = master

    def pick(self, useActive=True):
        if not useActive or not ColorManager.ACTIVE:
            # 0 = rgb tuple, 1=hex str
            ColorManager.ACTIVE = self.define(colorchooser.askcolor()[1])
        elif ColorManager.ACTIVE not in self.colors:
            self.define(ColorManager.ACTIVE)
        return ColorManager.ACTIVE

    def setActive(self, event, color: str):
        print(f"Setting color: {color}")
        ColorManager.ACTIVE = color

    def define(self, color: str):
        tagname = f"color={color}"
        if color.startswith("#{"):
            self.master.tag_config(tagname, background="#ff00ff")
        else:
            self.master.tag_config(tagname, foreground=color)
        self.master.tag_bind(tagname, "<Button-3>", partial(self.setActive, color=color))
        self.colors.add(color)
        return color


class TextBox(tk.Text):
    """A tk Text widget with extra features"""

    DEFAULT_WIDTH = 54
    DEFAULT_HEIGHT = 4

    # todo: maybe move color to post_init and pass through init itself to tk
    def __init__(self, parent, size: tuple[int] = (None, None), editable:bool = False, font: fonts.Font = None, **kwargs) -> None:
        super().__init__(
            parent,
            width=size[0] or TextBox.DEFAULT_WIDTH,
            height=size[1] or TextBox.DEFAULT_HEIGHT,
            font=font or fonts.DEFAULT,
            state="normal" if editable else "disabled",
            **kwargs
        )
        self.tkRoot = None
        self._editable = self._enabled = editable
        self.tag_config("b", font=fonts.BOLD)
        self.tag_config("i", font=fonts.ITALIC)
        self.color = ColorManager(self)
        self.bind("<Alt-Right>", self.copy_block)

        if editable:
            self.config(undo=True)
            self.spellChecker = SpellCheck(self)
            # Move default class binds last to allow overwriting
            this, cls, toplevel, all = self.bindtags()
            self.bindtags((this, toplevel, all, cls))
            # Keybinds
            self.bind("<Alt-x>", self.char_convert)
            self.bind("<Control-BackSpace>", self.del_word)
            self.bind("<Control-Shift-BackSpace>", self.del_word)
            self.bind("<Control-Delete>", self.del_word)
            self.bind("<Control-Shift-Delete>", self.del_word)
            self.bind("<Control-i>", self.format_text)
            self.bind("<Control-b>", self.format_text)
            self.bind("<Control-C>", self.format_text)
            self.bind("<Control-Shift-Up>", lambda e: self.moveLine(e, -1))
            self.bind("<Control-Shift-Down>", lambda e: self.moveLine(e, 1))

    def loadRichText(self, text: str = None):
        """Load text into widget, converting unity RT markup to tk tags.
        If no text is given it converts all existing text"""
        if not self._editable:
            self.setActive(True)
        if text is None:
            text = self.get(1.0, tk.END)
        tagList = list()
        offset = 0
        openedTags = dict()
        tagRe = r"<(/?)(([a-z]+)=?([#a-z\d{}]+)?)>"
        for m in re.finditer(tagRe, text, flags=re.IGNORECASE):
            isClose, fullTag, tagName, tagVal = m.groups()
            if tagName not in ("color", "b", "i", "size"):
                continue
            if isClose:
                openedTags[tagName]["end"] = m.start() - offset
            else:
                tagList.append({"name": fullTag, "value": tagVal, "start": m.start() - offset})
                openedTags[tagName] = tagList[-1]
                if tagName == "color":
                    self.color.define(tagVal)
            offset += len(m[0])
        # Add the cleaned text
        setText(self, re.sub(tagRe, "", text, flags=re.IGNORECASE))
        # Apply tags
        for toTag in tagList:
            self.tag_add(toTag["name"], f"1.0+{toTag['start']}c", f"1.0+{toTag['end']}c")
        if self._editable:
            self.spellChecker.check_spelling()
        else:
            self.setActive(False)

    def toRichText(self):
        text = list(self.get(1.0, tk.END))
        offset = 0
        tagList = list()
        for tag in self.tag_names():
            tagBaseName = tag.split("=")[0]
            if tagBaseName not in ("i", "b", "color", "size"):
                continue
            ranges = self.tag_ranges(tag)
            tagList.extend((text_count(self, "1.0", x, "-chars"), f"<{tag}>") for x in ranges[0::2])
            tagList.extend(
                (text_count(self, "1.0", x, "-chars"), f"</{tagBaseName}>") for x in ranges[1::2]
            )
        tagList.sort(key=lambda x: x[0])
        for idx, tag in tagList:
            text.insert(idx + offset, tag)
            offset += 1
        return "".join(text)
    
    def clear(self):
        wasEnabled = self._enabled
        if not wasEnabled:
            self.setActive(True)
        clearText(self)
        if not wasEnabled:
            self.setActive(False)

    def setActive(self, state:bool):
        if self._enabled == state:
            return
        self._enabled = state  # keep a simple bool, gdi tk
        self.config(state="normal" if state else "disabled")

    def copy_block(self, event=None):
        """Copies the text of this block or its parent to the clipboard"""
        if self.tkRoot is None:
            return
        self.tkRoot.clipboard_clear()
        self.tkRoot.clipboard_append(
            getText(getattr(self, "linkedTextBox", self)).replace("\r", "")
        )

    def linkTo(self, target:"TextBox", root: tk.Tk):
        self.linkedTextBox = target
        self.tkRoot = root


class TextBoxEditable(TextBox):
    def __init__(self, parent, size: tuple[int] = (None, None), font: fonts.Font = None, **kwargs) -> None:
        super().__init__(parent, size, True, font, **kwargs)
    
    def format_text(self, event):
        if not self.tag_ranges("sel"):
            print("No selection to format.")
            return
        currentTags = self.tag_names(tk.SEL_FIRST)
        if event.keysym == "i":
            if "i" in currentTags:
                self.tag_remove("i", tk.SEL_FIRST, tk.SEL_LAST)
            else:
                self.tag_add("i", tk.SEL_FIRST, tk.SEL_LAST)
        elif event.keysym == "b":
            if "b" in currentTags:
                self.tag_remove("b", tk.SEL_FIRST, tk.SEL_LAST)
            else:
                self.tag_add("b", tk.SEL_FIRST, tk.SEL_LAST)
        elif event.keysym == "C":
            color = f"color={self.color.pick(not (event.state & 131072))}"  # alt
            if color is None:
                return
            if color in currentTags:
                self.tag_remove(color, tk.SEL_FIRST, tk.SEL_LAST)
            else:
                self.tag_add(color, tk.SEL_FIRST, tk.SEL_LAST)
        else:
            return
        return "break"  # prevent control char entry

    def del_word(self, event):
        shift = event.state & 0x0001
        if event.keycode == 8:  # backspace
            ptn = r"^" if shift else r"[^ …—\.?!]+|^"
            sIdx = self.search(ptn, index=tk.INSERT, backwards=True, regexp=True, nocase=True)
            self.delete(sIdx, tk.INSERT)  # 
        elif event.keycode == 46:  # delete
            ptn = r".$" if shift else r" ?.(?=[ …—\.?!]|$)"
            sIdx = self.search(ptn, index=tk.INSERT, backwards=False, regexp=True, nocase=True)
            self.delete(tk.INSERT, sIdx + "+1c")
        return "break"

    def char_convert(self, event=None):
        pos = self.index(tk.INSERT)
        start = pos + "-6c"
        txt = self.get(start, pos)
        m = re.search(r"[A-Z0-9]+", txt)
        if m:
            try:
                res = chr(int(m.group(0), 16))
            except ValueError:
                return
            self.replace(f"{start}+{str(m.start())}c", pos, res)
        return "break"
    
    def moveLine(self, event, dir: int):
        text = getText(self).split("\n")[:-1]  # tk newline
        curIdx = int(self.index(tk.INSERT).split(".")[0]) - 1
        newIdx = (curIdx + dir) % len(text)
        curLine = text[curIdx]
        text[curIdx] = text[newIdx]
        text[newIdx] = curLine
        setText(self, "\n".join(text))
        self.mark_set(tk.INSERT, f"{newIdx + 1}.0")
        return "break"


def process_text(file: "TranslationFile", text: str = None, redoNewlines: bool = False):
    """Process given text or whole file when no text given.
    When whole file, assumes line lengths are correct and skips adjustment."""
    import textprocess

    opts = {"redoNewlines": redoNewlines, "replaceMode": "limit", "lineLength": -1, "targetLines": 99}
    if text:
        return textprocess.processText(file, text, opts)
    else:
        opts["lineLength"] = 0
        for block in file.genTextContainers():
            if len(block["enText"]) == 0 or "skip" in block:
                continue
            block["enText"] = textprocess.processText(file, block["enText"], opts)


# https://github.com/python/cpython/issues/97928
def text_count(widget, index1, index2, *options):
    return widget.tk.call((widget._w, "count") + options + (index1, index2))


def for_display(file, text):
    if file.escapeNewline:
        return re.sub(r"(?:\\[rn])+", "\n", text)
    else:
        return text.replace("\r", "")


def for_storage(file, text):
    return normalize(text, "\\n" if file.escapeNewline else "\n")


def normalize(text: str, newline: str = "\n"):
    return f" {newline}".join([line.strip() for line in text.strip().split("\n")])


def getText(widget: TkDisplaysText):
    """Return the full text of supported widgets."""
    if isinstance(widget, tk.Label):
        return widget.cget("text")
    elif isinstance(widget, tk.Entry):
        return widget.get(0, tk.END)
    elif isinstance(widget, tk.Text):
        return widget.get(1.0, tk.END)


def setText(widget: TkDisplaysText, text: str):
    """Sets full text of supported widgets."""
    if isinstance(widget, tk.Label):
        widget.config(text=text)
    else:
        clearText(widget)
        if isinstance(widget, tk.Entry):
            widget.insert(0, text)
        elif isinstance(widget, tk.Text):
            widget.insert(1.0, text)
        else:
            raise ValueError


def clearText(widget: TkDisplaysText):
    """Clears all text from widget"""
    if isinstance(widget, tk.Label):
        widget.config(text="")
    elif isinstance(widget, tk.Entry):
        widget.delete(0, tk.END)
    elif isinstance(widget, tk.Text):
        widget.delete(1.0, tk.END)
    else:
        raise ValueError
