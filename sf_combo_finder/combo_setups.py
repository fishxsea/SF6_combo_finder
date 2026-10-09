"""Readable requirements from published setups and explicit move inputs."""
import re


def route_requirements(finder, combo):
    conditions = combo.get('conditions', {})
    published = combo.get('evidence', {}).get('kind') == 'published_recipe'
    labels = []
    if published:
        position = conditions.get('position')
        if position == 'corner':
            labels.append('Corner route' if combo['evidence'].get('complete') else 'Corner recipe setup')
        elif position == 'midscreen':
            labels.append('Midscreen route')
        elif position == 'any':
            labels.append('Any position')
    if conditions.get('opponent_state', finder.opponent_state) == 'airborne':
        labels.append('Airborne start')
    hit_type = conditions.get('hit_type', finder.hit_type)
    if hit_type != 'normal':
        labels.append({'counter': 'Counter hit', 'punish_counter': 'Punish counter'}[hit_type])
    if conditions.get('opponent_poisoned', finder.opponent_poisoned):
        labels.append('Starts poisoned')
    posture = conditions.get('opponent_posture', 'any') if published else 'any'
    if posture != 'any':
        labels.append(f'{posture.capitalize()} target')
    notes = ' '.join(combo.get('notes', [])) if published else ''
    for pattern, label in (
            (r'\bclose[- ]range\b', 'Close range'),
            (r'opponent must be standing', 'Standing at conversion'),
            (r'\b(?:high enough|near the top|above A\.K\.I\.)', 'Height sensitive'),
            (r'\b(?:delay(?:ed)?|briefly|micro[- ]?walk)\b', 'Timing adjustment')):
        if re.search(pattern, notes, re.I):
            labels.append(label)
    moves = [finder.moves[key] for key in combo['moves']]
    if any(move['category'] == 'jump_normal' for move in moves):
        labels.append('Jump-in')
    for token, label in (('DRC(', 'Drive Rush Cancel'), ('DR(', 'Drive Rush'),
                         ('walk', 'Walk adjustment'), ('[', 'Charge required')):
        if any(token.lower() in move['input']['sf'].lower() for move in moves):
            labels.append(label)
    if any(move.get('category') == 'stance' or
           re.search(r'\b(?:stance|Sinister Slide|Serenity Stream)\b', move['name'], re.I)
           for move in moves):
        labels.append('Stance transition')
    return list(dict.fromkeys(labels))


def variation_label(conditions):
    parts = [{'corner': 'Corner', 'midscreen': 'Midscreen', 'any': 'Any position'}[conditions['position']]]
    if conditions['opponent_state'] == 'airborne':
        parts.append('Airborne start')
    if conditions['hit_type'] != 'normal':
        parts.append({'counter': 'Counter hit', 'punish_counter': 'Punish counter'}[conditions['hit_type']])
    if conditions['opponent_poisoned']:
        parts.append('Starts poisoned')
    if conditions.get('opponent_posture', 'any') != 'any':
        parts.append(conditions['opponent_posture'].capitalize())
    return ' / '.join(parts)
