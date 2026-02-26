#!/usr/bin/env python3
import json

with open('/Users/george/Code/anki-disambiguate/agents/agent2_vocab/selected_cards.json') as f:
    cards = json.load(f)

phase2_domains = {'play', 'food', 'family', 'animals', 'body', 'colours', 'actions', 'numbers', 'toys', 'location'}
phase1_domains = {'greetings', 'social', 'questions', 'feelings'}

def old_phase(priority, domains, status):
    if priority >= 8: return '1'
    if (priority >= 7 and bool(phase1_domains.intersection(set(domains))) and status == 'new'): return '1'
    if priority >= 5 and bool({'play','food','family','animals','body','colours'}.union(phase1_domains).intersection(set(domains))): return '2'
    return '3'

def new_phase(priority, domains, status):
    domain_set = set(domains)
    if priority >= 8: return '1'
    if (priority >= 7 and bool(phase1_domains.intersection(domain_set)) and status == 'new'): return '1'
    if 5 <= priority < 8 and bool(phase2_domains.union(phase1_domains).intersection(domain_set)): return '2'
    return '3'

changes = []
for c in cards:
    p = c['priority_score']
    d = c.get('child_domains', [])
    s = c.get('scheduling_status', 'new')
    old = old_phase(p, d, s)
    new = new_phase(p, d, s)
    if old != new:
        changes.append((c['fields']['Word'], old, new, p, d))

print(f'Notes needing phase update: {len(changes)}')
print('Changes:')
for w, o, n, p, d in changes[:30]:
    print(f'  {w}: {o} -> {n} (priority={p}, domains={d})')
