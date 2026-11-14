package service

import "slices"

func containsString(list []string, item string) bool { return slices.Contains(list, item) }

func sortStrings(values []string) { slices.Sort(values) }
