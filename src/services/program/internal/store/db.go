package store

import (
	"context"
	"strings"
)

type Item = map[string]any

type Key struct {
	PK string
	SK string
}

type Table string

type Tables struct {
	Health       Table
	Sessions     Table
	Supplements  Table
	Competitions Table
	Templates    Table
}

type GetOptions struct {
	Consistent bool
	Projection []string
}

type Query struct {
	Table      Table
	Index      string
	PKAttr     string
	PK         string
	SKAttr     string
	Prefix     string
	Between    *[2]string
	AtLeast    string
	AtMost     string
	Consistent bool
}

type DB interface {
	Get(ctx context.Context, table Table, key Key, options GetOptions) (Item, error)
	Put(ctx context.Context, table Table, item Item) error
	Query(ctx context.Context, query Query) ([]Item, error)
	BatchPut(ctx context.Context, table Table, items []Item) error
	BatchDelete(ctx context.Context, table Table, keys []Key) error
	SaveProgram(ctx context.Context, tables Tables, athlete string, program Item, expectedSK, currentBlockID, now, importID, importClaim string) error
}

func (q Query) skAttr() string {
	if q.SKAttr != "" {
		return q.SKAttr
	}
	return "sk"
}

func (q Query) pkAttr() string {
	if q.PKAttr != "" {
		return q.PKAttr
	}
	return "pk"
}

func (q Query) matches(sk string) bool {
	switch {
	case q.Between != nil:
		return sk >= q.Between[0] && sk <= q.Between[1]
	case q.AtLeast != "":
		return sk >= q.AtLeast
	case q.AtMost != "":
		return sk <= q.AtMost
	case q.Prefix != "":
		return strings.HasPrefix(sk, q.Prefix)
	}
	return true
}
