package fakedb

import (
	"fmt"
	"math/big"
	"strings"
	"unicode"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type attrs = map[string]types.AttributeValue

type env struct {
	names  map[string]string
	values map[string]types.AttributeValue
}

type token struct {
	kind string
	text string
}

func tokenize(source string) ([]token, error) {
	var out []token
	runes := []rune(source)
	for i := 0; i < len(runes); {
		r := runes[i]
		switch {
		case unicode.IsSpace(r):
			i++
		case r == '(' || r == ')' || r == ',' || r == '=' || r == '+' || r == '-':
			out = append(out, token{"sym", string(r)})
			i++
		case r == '<' || r == '>':
			text := string(r)
			if i+1 < len(runes) && (runes[i+1] == '=' || (r == '<' && runes[i+1] == '>')) {
				text += string(runes[i+1])
				i++
			}
			out = append(out, token{"sym", text})
			i++
		case r == '#' || r == ':' || unicode.IsLetter(r) || r == '_':
			start := i
			i++
			for i < len(runes) && (unicode.IsLetter(runes[i]) || unicode.IsDigit(runes[i]) || runes[i] == '_') {
				i++
			}
			text := string(runes[start:i])
			kind := "ident"
			switch r {
			case '#':
				kind = "name"
			case ':':
				kind = "value"
			}
			out = append(out, token{kind, text})
		default:
			return nil, fmt.Errorf("unexpected %q in %q", r, source)
		}
	}
	return out, nil
}

type parser struct {
	tokens []token
	pos    int
	env    env
}

func (p *parser) peek() token {
	if p.pos < len(p.tokens) {
		return p.tokens[p.pos]
	}
	return token{}
}

func (p *parser) next() token {
	t := p.peek()
	p.pos++
	return t
}

func (p *parser) keyword(word string) bool {
	t := p.peek()
	if t.kind == "ident" && strings.EqualFold(t.text, word) {
		p.pos++
		return true
	}
	return false
}

func (p *parser) symbol(text string) bool {
	t := p.peek()
	if t.kind == "sym" && t.text == text {
		p.pos++
		return true
	}
	return false
}

func (p *parser) expect(text string) error {
	if !p.symbol(text) {
		return fmt.Errorf("expected %q at %d", text, p.pos)
	}
	return nil
}

type operand struct {
	path  string
	value types.AttributeValue
	isVal bool
}

func (p *parser) operand() (operand, error) {
	t := p.next()
	switch t.kind {
	case "value":
		v, ok := p.env.values[t.text]
		if !ok {
			return operand{}, fmt.Errorf("missing value %s", t.text)
		}
		return operand{value: v, isVal: true}, nil
	case "name":
		name, ok := p.env.names[t.text]
		if !ok {
			return operand{}, fmt.Errorf("missing name %s", t.text)
		}
		return operand{path: name}, nil
	case "ident":
		return operand{path: t.text}, nil
	}
	return operand{}, fmt.Errorf("bad operand %q", t.text)
}

func (o operand) resolve(item attrs) (types.AttributeValue, bool) {
	if o.isVal {
		return o.value, true
	}
	v, ok := item[o.path]
	return v, ok
}

func (p *parser) orExpr(item attrs) (bool, error) {
	left, err := p.andExpr(item)
	if err != nil {
		return false, err
	}
	for p.keyword("OR") {
		right, err := p.andExpr(item)
		if err != nil {
			return false, err
		}
		left = left || right
	}
	return left, nil
}

func (p *parser) andExpr(item attrs) (bool, error) {
	left, err := p.term(item)
	if err != nil {
		return false, err
	}
	for p.keyword("AND") {
		right, err := p.term(item)
		if err != nil {
			return false, err
		}
		left = left && right
	}
	return left, nil
}

func (p *parser) term(item attrs) (bool, error) {
	if p.keyword("NOT") {
		inner, err := p.term(item)
		return !inner, err
	}
	if p.symbol("(") {
		inner, err := p.orExpr(item)
		if err != nil {
			return false, err
		}
		return inner, p.expect(")")
	}
	if t := p.peek(); t.kind == "ident" && p.pos+1 < len(p.tokens) && p.tokens[p.pos+1].text == "(" {
		return p.function(item)
	}
	left, err := p.operand()
	if err != nil {
		return false, err
	}
	if p.keyword("BETWEEN") {
		low, err := p.operand()
		if err != nil {
			return false, err
		}
		if !p.keyword("AND") {
			return false, fmt.Errorf("BETWEEN needs AND")
		}
		high, err := p.operand()
		if err != nil {
			return false, err
		}
		l, lok := left.resolve(item)
		lo, _ := low.resolve(item)
		hi, _ := high.resolve(item)
		if !lok {
			return false, nil
		}
		return compare(l, lo) >= 0 && compare(l, hi) <= 0, nil
	}
	op := p.next()
	if op.kind != "sym" {
		return false, fmt.Errorf("expected comparison, got %q", op.text)
	}
	right, err := p.operand()
	if err != nil {
		return false, err
	}
	l, lok := left.resolve(item)
	r, rok := right.resolve(item)
	if !lok || !rok {
		return op.text == "<>", nil
	}
	switch op.text {
	case "=":
		return compare(l, r) == 0, nil
	case "<>":
		return compare(l, r) != 0, nil
	case "<":
		return compare(l, r) < 0, nil
	case "<=":
		return compare(l, r) <= 0, nil
	case ">":
		return compare(l, r) > 0, nil
	case ">=":
		return compare(l, r) >= 0, nil
	}
	return false, fmt.Errorf("unsupported operator %q", op.text)
}

func (p *parser) function(item attrs) (bool, error) {
	name := strings.ToLower(p.next().text)
	if err := p.expect("("); err != nil {
		return false, err
	}
	first, err := p.operand()
	if err != nil {
		return false, err
	}
	var second operand
	if p.symbol(",") {
		if second, err = p.operand(); err != nil {
			return false, err
		}
	}
	if err := p.expect(")"); err != nil {
		return false, err
	}
	v, present := first.resolve(item)
	switch name {
	case "attribute_exists":
		return present, nil
	case "attribute_not_exists":
		return !present, nil
	case "begins_with":
		arg, _ := second.resolve(item)
		s, ok1 := v.(*types.AttributeValueMemberS)
		prefix, ok2 := arg.(*types.AttributeValueMemberS)
		return present && ok1 && ok2 && strings.HasPrefix(s.Value, prefix.Value), nil
	case "contains":
		arg, _ := second.resolve(item)
		if !present {
			return false, nil
		}
		switch typed := v.(type) {
		case *types.AttributeValueMemberSS:
			s, ok := arg.(*types.AttributeValueMemberS)
			if !ok {
				return false, nil
			}
			for _, entry := range typed.Value {
				if entry == s.Value {
					return true, nil
				}
			}
		case *types.AttributeValueMemberL:
			for _, entry := range typed.Value {
				if compare(entry, arg) == 0 {
					return true, nil
				}
			}
		case *types.AttributeValueMemberS:
			s, ok := arg.(*types.AttributeValueMemberS)
			return ok && strings.Contains(typed.Value, s.Value), nil
		}
		return false, nil
	}
	return false, fmt.Errorf("unsupported function %s", name)
}

func evalCondition(source string, e env, item attrs) (bool, error) {
	if strings.TrimSpace(source) == "" {
		return true, nil
	}
	tokens, err := tokenize(source)
	if err != nil {
		return false, err
	}
	p := &parser{tokens: tokens, env: e}
	ok, err := p.orExpr(item)
	if err != nil {
		return false, err
	}
	if p.pos != len(tokens) {
		return false, fmt.Errorf("trailing tokens in %q", source)
	}
	return ok, nil
}

func compare(a, b types.AttributeValue) int {
	switch left := a.(type) {
	case *types.AttributeValueMemberS:
		if right, ok := b.(*types.AttributeValueMemberS); ok {
			return strings.Compare(left.Value, right.Value)
		}
	case *types.AttributeValueMemberN:
		if right, ok := b.(*types.AttributeValueMemberN); ok {
			l, _ := new(big.Rat).SetString(left.Value)
			r, _ := new(big.Rat).SetString(right.Value)
			if l != nil && r != nil {
				return l.Cmp(r)
			}
		}
	case *types.AttributeValueMemberBOOL:
		if right, ok := b.(*types.AttributeValueMemberBOOL); ok && left.Value == right.Value {
			return 0
		}
	case *types.AttributeValueMemberNULL:
		if _, ok := b.(*types.AttributeValueMemberNULL); ok {
			return 0
		}
	case *types.AttributeValueMemberL:
		if right, ok := b.(*types.AttributeValueMemberL); ok && len(left.Value) == len(right.Value) {
			for i := range left.Value {
				if compare(left.Value[i], right.Value[i]) != 0 {
					return 1
				}
			}
			return 0
		}
	case *types.AttributeValueMemberM:
		if right, ok := b.(*types.AttributeValueMemberM); ok && len(left.Value) == len(right.Value) {
			for key, v := range left.Value {
				other, present := right.Value[key]
				if !present || compare(v, other) != 0 {
					return 1
				}
			}
			return 0
		}
	case *types.AttributeValueMemberSS:
		if right, ok := b.(*types.AttributeValueMemberSS); ok && len(left.Value) == len(right.Value) {
			seen := map[string]bool{}
			for _, entry := range left.Value {
				seen[entry] = true
			}
			for _, entry := range right.Value {
				if !seen[entry] {
					return 1
				}
			}
			return 0
		}
	}
	return 2
}

func applyUpdate(source string, e env, item attrs) error {
	tokens, err := tokenize(source)
	if err != nil {
		return err
	}
	p := &parser{tokens: tokens, env: e}
	for p.pos < len(tokens) {
		switch {
		case p.keyword("SET"):
			for {
				target, err := p.operand()
				if err != nil {
					return err
				}
				if err := p.expect("="); err != nil {
					return err
				}
				v, err := p.setValue(item)
				if err != nil {
					return err
				}
				item[target.path] = v
				if !p.symbol(",") {
					break
				}
			}
		case p.keyword("ADD"):
			for {
				target, err := p.operand()
				if err != nil {
					return err
				}
				add, err := p.operand()
				if err != nil {
					return err
				}
				if err := addTo(item, target.path, add.value); err != nil {
					return err
				}
				if !p.symbol(",") {
					break
				}
			}
		case p.keyword("REMOVE"):
			for {
				target, err := p.operand()
				if err != nil {
					return err
				}
				delete(item, target.path)
				if !p.symbol(",") {
					break
				}
			}
		default:
			return fmt.Errorf("unsupported update clause at %q", p.peek().text)
		}
	}
	return nil
}

func addTo(item attrs, path string, add types.AttributeValue) error {
	switch typed := add.(type) {
	case *types.AttributeValueMemberSS:
		existing, _ := item[path].(*types.AttributeValueMemberSS)
		merged := &types.AttributeValueMemberSS{}
		seen := map[string]bool{}
		if existing != nil {
			for _, entry := range existing.Value {
				seen[entry] = true
				merged.Value = append(merged.Value, entry)
			}
		}
		for _, entry := range typed.Value {
			if !seen[entry] {
				merged.Value = append(merged.Value, entry)
			}
		}
		item[path] = merged
		return nil
	case *types.AttributeValueMemberN:
		current, _ := item[path].(*types.AttributeValueMemberN)
		sum := new(big.Rat)
		if current != nil {
			sum.SetString(current.Value)
		}
		delta, _ := new(big.Rat).SetString(typed.Value)
		sum.Add(sum, delta)
		item[path] = &types.AttributeValueMemberN{Value: sum.FloatString(0)}
		return nil
	}
	return fmt.Errorf("ADD unsupported for %T", add)
}

func (p *parser) setValue(item attrs) (types.AttributeValue, error) {
	t := p.peek()
	if t.kind == "ident" && p.pos+1 < len(p.tokens) && p.tokens[p.pos+1].text == "(" {
		name := strings.ToLower(p.next().text)
		p.next()
		switch name {
		case "if_not_exists":
			path, err := p.operand()
			if err != nil {
				return nil, err
			}
			if err := p.expect(","); err != nil {
				return nil, err
			}
			fallback, err := p.setValue(item)
			if err != nil {
				return nil, err
			}
			if err := p.expect(")"); err != nil {
				return nil, err
			}
			if existing, ok := path.resolve(item); ok {
				return existing, nil
			}
			return fallback, nil
		case "list_append":
			first, err := p.setValue(item)
			if err != nil {
				return nil, err
			}
			if err := p.expect(","); err != nil {
				return nil, err
			}
			second, err := p.setValue(item)
			if err != nil {
				return nil, err
			}
			if err := p.expect(")"); err != nil {
				return nil, err
			}
			l, _ := first.(*types.AttributeValueMemberL)
			r, _ := second.(*types.AttributeValueMemberL)
			out := &types.AttributeValueMemberL{}
			if l != nil {
				out.Value = append(out.Value, l.Value...)
			}
			if r != nil {
				out.Value = append(out.Value, r.Value...)
			}
			return out, nil
		}
		return nil, fmt.Errorf("unsupported function %s", name)
	}
	o, err := p.operand()
	if err != nil {
		return nil, err
	}
	v, ok := o.resolve(item)
	if !ok {
		return nil, fmt.Errorf("unresolved %s", o.path)
	}
	return v, nil
}
