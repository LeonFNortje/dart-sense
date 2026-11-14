import copy

IN_MODES = ('straight', 'double', 'master')
OUT_MODES = ('double', 'master', 'straight')
IMPOSSIBLE_SCORES = {163, 166, 169, 172, 173, 175, 176, 178, 179}


def dart_value(dart):
    if dart == 'DB':
        return 50
    if dart == 'SB':
        return 25
    if dart == 'miss' or not dart:
        return 0
    multiplier = {'S': 1, 'D': 2, 'T': 3}[dart[0]]
    return multiplier * int(dart[1:])


def qualifies(dart, mode):
    # whether a dart can open (double/master in) or finish (double/master out) a leg
    if mode == 'straight':
        return dart != 'miss'
    is_double = dart == 'DB' or dart.startswith('D')
    if mode == 'double':
        return is_double
    return is_double or dart.startswith('T') # master: double or treble


class Match:
    """x01 match: legs or sets, first to / best of, straight/double/master in and out."""

    def __init__(self, players, start_score=501, target=3, unit='legs', match_format='first_to',
                 in_mode='straight', out_mode='double', legs_per_set=3, first_player=0):
        assert 1 <= len(players) <= 8, 'between 1 and 8 players'
        assert unit in ('legs', 'sets') and match_format in ('first_to', 'best_of')
        assert in_mode in IN_MODES and out_mode in OUT_MODES
        self.players = list(players)
        self.n = len(players)
        self.start_score = int(start_score)
        self.target = int(target)
        self.unit = unit
        self.match_format = match_format
        self.in_mode = in_mode
        self.out_mode = out_mode
        self.legs_per_set = legs_per_set # sets are first to this many legs
        self.to_win = self.target if match_format == 'first_to' else self.target // 2 + 1

        self.sets_won = [0] * self.n
        self.legs_won = [0] * self.n # legs in the current set (or in the match, when playing legs)
        self.set_no, self.leg_no = 1, 1
        self.leg_starter = first_player
        self.history = [] # one dict per visit, whole match
        self.winner = None
        self._undo = []
        self._start_leg(first_player)

    def _start_leg(self, starter):
        self.leg_starter = starter
        self.current = starter
        self.scores = [self.start_score] * self.n
        self.opened = [self.in_mode == 'straight'] * self.n

    def evaluate(self, darts, player=None):
        """Score a visit (list like ['T20', 'S5']) for a player without applying it."""
        p = self.current if player is None else player
        remaining, opened, scored = self.scores[p], self.opened[p], 0
        result = {'scored': 0, 'remaining': remaining, 'bust': False, 'checkout': False, 'darts_used': len(darts), 'opened': opened}
        for i, dart in enumerate(darts):
            if not opened:
                if not qualifies(dart, self.in_mode):
                    continue
                opened = True
            scored += dart_value(dart)
            left = remaining - scored
            if left < 0 or (left == 1 and self.out_mode != 'straight') or (left == 0 and not qualifies(dart, self.out_mode)):
                result.update(bust=True, scored=scored, remaining=remaining, darts_used=i + 1, opened=self.opened[p])
                return result
            if left == 0:
                result.update(checkout=True, scored=scored, remaining=0, darts_used=i + 1, opened=True)
                return result
        result.update(scored=scored, remaining=remaining - scored, opened=opened)
        return result

    def visit_from_darts(self, darts):
        darts = [d for d in darts if d]
        return self._apply(self.evaluate(darts), darts)

    def visit_from_total(self, points, darts_used=3):
        """Manual entry of a visit total. Finishing/opening darts can't be checked, so they are assumed valid."""
        points = int(points)
        if points < 0 or points > 180 or points in IMPOSSIBLE_SCORES:
            raise ValueError(f'{points} is not a possible visit score')
        p = self.current
        remaining = self.scores[p] - points
        result = {'scored': points, 'remaining': remaining, 'bust': False, 'checkout': False,
                  'darts_used': darts_used, 'opened': self.opened[p] or points > 0}
        if remaining < 0 or (remaining == 1 and self.out_mode != 'straight'):
            result.update(bust=True, remaining=self.scores[p], opened=self.opened[p])
        elif remaining == 0:
            result['checkout'] = True
        return self._apply(result, None)

    def _apply(self, result, darts):
        if self.winner is not None:
            raise RuntimeError('match is over')
        self._undo.append(copy.deepcopy({k: v for k, v in self.__dict__.items() if k != '_undo'}))
        p = self.current
        visit = {'player': p, 'set': self.set_no, 'leg': self.leg_no, 'darts': darts,
                 'scored': 0 if result['bust'] else result['scored'], 'attempted': result['scored'],
                 'remaining': result['remaining'], 'bust': result['bust'], 'checkout': result['checkout'],
                 'darts_used': result['darts_used'] if result['checkout'] else 3}
        self.history.append(visit)
        self.opened[p] = result['opened']
        self.scores[p] = result['remaining']
        visit['event'] = self._after_checkout(p) if result['checkout'] else None
        if not result['checkout']:
            self.current = (self.current + 1) % self.n
        return visit

    def _after_checkout(self, p):
        self.legs_won[p] += 1
        if self.unit == 'legs':
            if self.legs_won[p] >= self.to_win:
                self.winner = p
                return 'match'
            self.leg_no += 1
            self._start_leg((self.leg_starter + 1) % self.n)
            return 'leg'
        if self.legs_won[p] >= self.legs_per_set:
            self.sets_won[p] += 1
            if self.sets_won[p] >= self.to_win:
                self.winner = p
                return 'match'
            self.set_no += 1
            self.leg_no = 1
            self.legs_won = [0] * self.n
            self._start_leg((self.leg_starter + 1) % self.n)
            return 'set'
        self.leg_no += 1
        self._start_leg((self.leg_starter + 1) % self.n)
        return 'leg'

    def undo(self):
        if not self._undo:
            return False
        undo_stack = self._undo
        self.__dict__.update(undo_stack.pop())
        self._undo = undo_stack
        return True

    def player_stats(self, p):
        visits = [v for v in self.history if v['player'] == p]
        leg_visits = [v for v in visits if v['set'] == self.set_no and v['leg'] == self.leg_no]
        darts = sum(v['darts_used'] for v in visits)
        return {
            'average': round(sum(v['scored'] for v in visits) / darts * 3, 2) if darts else 0.0,
            'last_score': visits[-1]['scored'] if visits else None,
            'darts_thrown': sum(v['darts_used'] for v in leg_visits),
        }

    def state(self):
        leg_history = [v for v in self.history if v['set'] == self.set_no and v['leg'] == self.leg_no]
        return {
            'players': [{'name': name, 'score': self.scores[i], 'legs': self.legs_won[i], 'sets': self.sets_won[i],
                         'opened': self.opened[i], **self.player_stats(i)} for i, name in enumerate(self.players)],
            'current': self.current, 'leg_starter': self.leg_starter,
            'set_no': self.set_no, 'leg_no': self.leg_no,
            'unit': self.unit, 'to_win': self.to_win, 'legs_per_set': self.legs_per_set,
            'in_mode': self.in_mode, 'out_mode': self.out_mode, 'start_score': self.start_score,
            'leg_history': leg_history,
            'winner': self.winner,
            'can_undo': bool(self._undo),
        }
