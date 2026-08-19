from __future__ import annotations
from html.parser import HTMLParser
import re
from aiogram.types import InlineKeyboardMarkup, InputRichBlockDivider, InputRichBlockList, InputRichBlockListItem, InputRichBlockParagraph, InputRichBlockSectionHeading, InputRichBlockTable, InputRichBlockDetails, InputRichMessage, Message, RichBlockTableCell, RichTextBold, RichTextItalic, RichTextUnderline, RichTextStrikethrough, RichTextCode, RichTextCustomEmoji, RichTextUrl

EM_T  = '<tg-emoji emoji-id="5330364803032583392">🪙</tg-emoji>'
EM_TC = '<tg-emoji emoji-id="5330246627007434971">🪙</tg-emoji>'

class HTMLToRichTextParser(HTMLParser):

    def __init__(self):
        super().__init__()
        self.stack = [[]]
        self.current_tags = []

    def handle_starttag(self, tag, attrs):
        self.stack.append([])
        self.current_tags.append((tag, dict(attrs)))

    def handle_endtag(self, tag):
        if not self.current_tags:
            return
        last_tag, attrs = self.current_tags.pop()
        children = self.stack.pop()
        content = children if len(children) > 1 else children[0] if children else ''
        if tag in ('b', 'strong'):
            node = RichTextBold(text=content)
        elif tag in ('i', 'em'):
            node = RichTextItalic(text=content)
        elif tag in ('u', 'ins'):
            node = RichTextUnderline(text=content)
        elif tag in ('s', 'strike', 'del'):
            node = RichTextStrikethrough(text=content)
        elif tag == 'code':
            node = RichTextCode(text=content)
        elif tag == 'a':
            node = RichTextUrl(text=content, url=attrs.get('href', ''))
        elif tag == 'tg-emoji':
            node = RichTextCustomEmoji(text=content, alternative_text=str(content), custom_emoji_id=attrs.get('emoji-id') or attrs.get('id', ''))
        else:
            node = content
        self.stack[-1].append(node)

    def handle_data(self, data):
        if data:
            self.stack[-1].append(data)

def parse_html_to_rich(html_str: str):
    if not html_str:
        return ''
    parser = HTMLToRichTextParser()
    parser.feed(str(html_str))
    res = parser.stack[0]
    return res if len(res) > 1 else res[0] if res else ''

def strip_tags(html_str: str) -> str:
    if not html_str:
        return ''
    return re.sub('<[^>]+>', '', str(html_str))

def heading(text: str) -> InputRichBlockSectionHeading:
    return InputRichBlockSectionHeading(text=parse_html_to_rich(text), size=3)

def para(text: str) -> InputRichBlockParagraph:
    return InputRichBlockParagraph(text=parse_html_to_rich(text))

def divider() -> InputRichBlockDivider:
    return InputRichBlockDivider()

def details(summary_text: str, blocks: list, is_open: bool=False) -> InputRichBlockDetails:
    return InputRichBlockDetails(summary=parse_html_to_rich(summary_text), blocks=blocks, is_open=is_open)

def table(headers: list[str], rows: list[list[str]], *, bordered: bool=True) -> InputRichBlockTable:
    cells = []
    if headers:
        cells.append([RichBlockTableCell(text=parse_html_to_rich(h), is_header=True, align='left', valign='middle') for h in headers])
    for row in rows:
        cells.append([RichBlockTableCell(text=parse_html_to_rich(str(c)), align='left', valign='middle') for c in row])
    return InputRichBlockTable(cells=cells, is_bordered=bordered)

def bullets(items: list[str]) -> InputRichBlockList:
    return InputRichBlockList(items=[InputRichBlockListItem(blocks=[InputRichBlockParagraph(text=parse_html_to_rich(t))]) for t in items])

async def send_rich(message: Message, blocks: list, reply_markup: InlineKeyboardMarkup | None=None) -> Message:
    return await message.bot.send_rich_message(chat_id=message.chat.id, rich_message=InputRichMessage(blocks=blocks), reply_markup=reply_markup)

async def send_rich_to(bot, chat_id: int | str, blocks: list, reply_markup: InlineKeyboardMarkup | None=None) -> Message:
    return await bot.send_rich_message(chat_id=chat_id, rich_message=InputRichMessage(blocks=blocks), reply_markup=reply_markup)