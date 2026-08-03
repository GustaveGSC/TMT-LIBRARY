from dataclasses import dataclass

from sqlalchemy import and_, not_, or_


class FilterExpressionError(ValueError):
    """可直接返回给物料筛选界面的表达式错误。"""


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str = ''


def _tokenize(text):
    tokens = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char in '&|!()':
            tokens.append(_Token(char))
            index += 1
            continue
        if char == '"':
            end = text.find('"', index + 1)
            if end < 0:
                raise FilterExpressionError('引号不匹配')
            value = text[index + 1:end]
            if not value.strip():
                raise FilterExpressionError('操作数不能为空')
            tokens.append(_Token('operand', value))
            index = end + 1
            continue
        end = index
        while end < len(text) and text[end] not in '&|!()"':
            end += 1
        value = text[index:end].strip()
        if not value:
            raise FilterExpressionError('操作数不能为空')
        tokens.append(_Token('operand', value))
        index = end
    return tokens


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.index = 0
        self.node_count = 0

    def _node(self, kind, *children):
        self.node_count += 1
        if self.node_count > 50:
            raise FilterExpressionError('表达式过于复杂')
        return kind, *children

    def _peek(self):
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def _take(self):
        token = self._peek()
        if token:
            self.index += 1
        return token

    def parse(self):
        if not self.tokens:
            raise FilterExpressionError('操作数不能为空')
        tree = self._expr(0)
        remaining = self._peek()
        if remaining:
            if remaining.kind == ')':
                raise FilterExpressionError('括号不匹配')
            raise FilterExpressionError('缺少操作数')
        return tree

    def _expr(self, depth):
        left = self._term(depth)
        while self._peek() and self._peek().kind == '|':
            self._take()
            left = self._node('or', left, self._term(depth))
        return left

    def _term(self, depth):
        left = self._factor(depth)
        while self._peek() and self._peek().kind == '&':
            self._take()
            left = self._node('and', left, self._factor(depth))
        return left

    def _factor(self, depth):
        token = self._peek()
        if token is None or token.kind in ('&', '|', ')'):
            raise FilterExpressionError('缺少操作数')
        if token.kind == '!':
            self._take()
            return self._node('not', self._factor(depth + 1))
        if token.kind == '(':
            if depth >= 10:
                raise FilterExpressionError('表达式过于复杂')
            self._take()
            if self._peek() and self._peek().kind == ')':
                raise FilterExpressionError('操作数不能为空')
            value = self._expr(depth + 1)
            if not self._peek() or self._take().kind != ')':
                raise FilterExpressionError('括号不匹配')
            return value
        self._take()
        return self._node('operand', token.value)


def parse_filter_expression(text):
    return _Parser(_tokenize(text)).parse()


def escape_like_literal(value):
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def literal_contains(column, value):
    return column.like(f'%{escape_like_literal(value)}%', escape='\\')


def expression_condition(column, text):
    def build(node):
        kind = node[0]
        if kind == 'operand':
            return literal_contains(column, node[1])
        if kind == 'not':
            return not_(build(node[1]))
        if kind == 'and':
            return and_(build(node[1]), build(node[2]))
        return or_(build(node[1]), build(node[2]))

    return build(parse_filter_expression(text))
