import sublime
import sublime_plugin


###----------------------------------------------------------------------------


# String constants for generating our grid of squares for the game board.
_grid_t = '/---v---v---\\'
_grid_b = '\\---^---^---/'
_grid_h = '>---+---+---<'
_grid_v = '|   |   |   |'

# Our sample puzzle
_puzzle = [
    [0, 0, 0,    0, 0, 4,    1, 8, 7],
    [8, 0, 0,    1, 0, 0,    6, 4, 0],
    [0, 1, 0,    0, 0, 0,    0, 2, 0],

    [9, 0, 0,    0, 1, 3,    0, 0, 4],
    [0, 5, 1,    0, 2, 0,    8, 0, 6],
    [3, 6, 7,    0, 0, 5,    2, 0, 0],

    [5, 9, 6,    0, 0, 0,    0, 0, 0],
    [0, 4, 0,    5, 9, 0,    0, 7, 0],
    [0, 7, 3,    4, 8, 1,    0, 0, 5]
]

# The state of answers in the puzzle (true is correct, false is wrong)
_state = [
    [True, True, True,    True, True, True,    True, True, True],
    [True, True, True,    True, True, True,    True, True, True],
    [True, True, True,    True, True, True,    True, True, True],

    [True, True, True,    True, True, True,    True, True, True],
    [True, True, True,    True, True, True,    True, True, True],
    [True, True, True,    True, True, True,    True, True, True],

    [True, True, True,    True, True, True,    True, True, True],
    [True, True, True,    True, True, True,    True, True, True],
    [True, True, True,    True, True, True,    True, True, True],
]

# The hint values set up for this field
_hints = [
    [ [], [], [],    [], [], [],    [], [], [] ],
    [ [], [], [],    [], [], [],    [], [], [] ],
    [ [], [], [],    [], [], [],    [], [], [] ],

    [ [], [], [],    [], [], [],    [], [], [] ],
    [ [], [], [],    [], [], [],    [], [], [] ],
    [ [], [], [],    [], [], [],    [], [], [] ],

    [ [], [], [],    [], [], [],    [], [], [] ],
    [ [], [], [],    [], [], [],    [], [], [] ],
    [ [], [], [],    [], [], [],    [], [], [] ],
]


###----------------------------------------------------------------------------


def _sudoku_syntax(file):
    """
    Return the full name of the given sudoku syntax based on the base name.
    """
    return "Packages/Sudoku/resources/syntax/%s.sublime-syntax" % file


def _is_sudoku(obj):
    """
    Given a window, view or settings object, return back an indication as to
    whether it represents a Sudoku game or not; for a window, the test applies
    to the active view in that window.
    """
    if isinstance(obj, sublime.Window):
        # Not sure why at the moment, but it's possible for a window to not
        # have an active view, so guard against that.
        if obj.active_view() is None:
            return False
        obj = obj.active_view().settings()
    elif isinstance(obj, sublime.View):
        obj = obj.settings()

    return (not obj.get("_debug", False) and
                obj.get("syntax", "") == _sudoku_syntax("Sudoku"))


def _make_grid():
    """
    Generate and return a game grid as a string.
    """
    t = " ".join([_grid_t] * 3) + "\n"
    b = " ".join([_grid_b] * 3) + "\n"
    h = " ".join([_grid_h] * 3) + "\n"
    v = " ".join([_grid_v] * 3) + "\n"

    r = (t + (v * 3) + h) + ((v * 3) + h) + ((v * 3) + b)
    g = ((r + "\n") * 3) + "\n"

    return g


###----------------------------------------------------------------------------


class SudokuNewGameCommand(sublime_plugin.ApplicationCommand):
    """
    Start a new Sudoku game; this spawns a new window for the game and creates
    an appropriate view inside of it to represent the game.
    """
    def run(self):
        sublime.run_command("new_window")
        window = sublime.active_window()

        # Make the window bare.
        window.set_minimap_visible(False)
        window.set_tabs_visible(False)
        window.set_menu_visible(False)
        window.set_status_bar_visible(False)

        # Set up the Sudoku view.
        view = window.new_file(syntax=_sudoku_syntax("Sudoku"))
        view.set_name("Sublime Sudoku")
        view.set_scratch(True)

        view.run_command("sudoku", {"action": "new_game"})

        # Finalize it now; from this point forward we need to adjust the read
        # only state in order to modify the view.
        view.set_read_only(True)
        view.sel().clear()


class SudokuBase():
    """
    This is the base class for our Sudoku game commands, and encapsulates all
    of the boilerplate logic needed by those commands.
    """
    def run(self, edit, action, **kwargs):
        # If we don't know where our game cells are yet, then try to capture
        # them now, and save them if we found them.
        if not hasattr(self, "cells"):
            cells = self.view.find_by_selector("meta.cell.corner")
            if cells:
                self.cells = cells
                # TODO: Calculculate the width and height based on the offsets
                self.cell_width = 5
                self.cell_height = 5

        # Save the edit object from this invocation for later method use just
        # for code clarity reasons; this can't be used after the command ends.
        self.edit = edit

        # Dispatch the command based on the action provided.
        method = getattr(self, '_' + action)
        if method:
            return method(**kwargs)

        sublime.message_dialog("Unknown Sudoku command '%s'" % action)

    def is_enabled(self, **kwargs):
        return self.view.match_selector(0, "text.plain.sudoku")

    def span(self, pos, offset, width):
        """
        Given a position tuple of (row, col) and an offset tuple, return back a
        region that starts at the offset position and has the given width.
        """
        pos = self.view.text_point(*pos)
        pos = tuple(map(sum, zip(self.view.rowcol(pos), offset)))
        pos = self.view.text_point(*pos)

        return sublime.Region(pos, pos + width)

    def frame(self, row, col):
        """
        Given a 0 based row and column, return back a list of regions that
        represent the frame surrounding that cell.
        """
        root = self.view.rowcol(self.cells[(row * 9) + col].begin())
        return (
            [self.span(root, (0, 0), self.cell_width)] +
            [self.span(root, (r, 0), 1) for r in range(1, self.cell_height - 1)] +
            [self.span(root, (r, self.cell_width - 1), 1) for r in range(1, self.cell_height - 1)] +
            [self.span(root, (self.cell_height - 1, 0), self.cell_width)])

    def content(self, row, col):
        """
        Given a 0 based row and column, return back a list of regions that
        represent the inner portion of that cell. This will be one region for
        each row in the cell.
        """
        root = self.view.rowcol(self.cells[(row * 9) + col].begin())
        return [self.span(root, (r, 1), self.cell_width - 2) for r in range(1, self.cell_height - 1)]

    def cell(self, region):
        """
        Given a region that represents the top left corner of a cell, return back
        the top left corner of the interior of that cell as a (row, col) tuple.
        """
        r, c = self.view.rowcol(region.a)
        return (r + 1, c + 1)

    def render(self, action, **kwargs):
        """
        Invoke the sudoku render command with the given action and arguments.
        """
        kwargs["action"] = action
        self.view.set_read_only(False)
        self.view.run_command("sudoku_render", kwargs)
        self.view.set_read_only(True)

    def persist(self, name, value):
        """
        Persist into the settings of the view the value provided.
        """
        self.view.settings().set("sudoku_" + name, value)

    def get(self, name, default=None):
        """
        Fetch from the view settings the value of the given name, using the
        default value given if the setting is not available.
        """
        return self.view.settings().get("sudoku_" + name, default)


class SudokuCommand(SudokuBase, sublime_plugin.TextCommand):
    """
    This command acts as the entry point into the game logic; the action given
    is used to drive the game and the actions taken by the user.
    """
    def _new_game(self):
        self.persist("puzzle", _puzzle)
        self.persist("state", _state)
        self.persist("hints", _hints)
        self.persist("current_pos", [4, 4])
        self.persist("hinting", False)

        self._redraw(complete=True)

    def _redraw(self, complete=False):
        puzzle = self.get("puzzle")
        state = self.get("state")
        hints = self.get("hints")
        pos = self.get("current_pos")
        hinting = self.get("hinting")

        if complete:
            self.render("grid")
        self.render("puzzle", puzzle=puzzle, state=state, hints=hints)
        self.render("hilight", row=pos[0], col=pos[1], hinting=hinting)

    def _move(self, row, col):
        current_pos = self.get("current_pos", [0, 0])
        new_pos = [
            max(0, min(current_pos[0] + row, 8)),
            max(0, min(current_pos[1] + col, 8))
            ]

        if new_pos != current_pos:
            self.persist("current_pos", new_pos)
            hinting = self.get("hinting", False)
            self.render("hilight", row=new_pos[0], col=new_pos[1], hinting=hinting)

    def _toggle_hinting(self):
        hinting = not self.get("hinting", False)
        self.persist("hinting", hinting)

        pos = self.get("current_pos", [0, 0])
        self.render("hilight", row=pos[0], col=pos[1], hinting=hinting)

    def _input(self, character):
        if character == " ":
            return self._toggle_hinting()

        correct = True
        shifted = "!@#$%^&*("
        if character in shifted:
            correct = False
            character = str(shifted.find(character) + 1)

        # TODO: Render only the current cell, not all cells
        if character.isdigit():
            user_hint = int(character)

            pos = self.get("current_pos")
            puzzle_data = self.get("puzzle")
            puzzle_state = self.get("state")

            # TODO: detect correctness and select state appropriately
            puzzle_data[pos[0]][pos[1]] = user_hint
            puzzle_state[pos[0]][pos[1]] = correct

            self.persist("puzzle", puzzle_data)
            self.persist("state", puzzle_state)
            self._redraw(complete=False)

    def _hint_input(self, character):
        if character == " ":
            return self._toggle_hinting()

        # TODO: Render only the current cell, not all cells
        if character.isdigit():
            user_hint = int(character)

            pos = self.get("current_pos")
            puzzle_data = self.get("puzzle")
            puzzle_hints = self.get("hints")

            hint_list = puzzle_hints[pos[0]][pos[1]]
            if user_hint and not puzzle_data[pos[0]][pos[1]]:
                if user_hint in hint_list:
                    hint_list.remove(user_hint)
                else:
                    hint_list.append(user_hint)

                self.persist("hints", puzzle_hints)
                self._redraw(complete=False)



class SudokuRenderCommand(SudokuBase, sublime_plugin.TextCommand):
    """
    Performs all "rendering" in the game view for us, based on the arguments
    provided. This allows a single command to cache the list of regions that
    know where the cells in the grid are situated.
    """
    def cell_fill(self, row, col, puzzle, state, hints):
        value = puzzle[row][col]
        correct = state[row][col]
        hint = hints[row][col]

        if value:
            text = "+%d+" if correct else "x%dx"
            return ["   ", text % value, "   "]

        if hint:
            result = ["", "", ""]
            for value in range(1, 10):
                c = "%d" % value if value in hint else " "
                result[(value - 1) // 3] += c

            return result

        return ["   ", "   ", "   "]

    def _grid(self):
        grid_region = sublime.Region(0, len(self.view))
        self.view.replace(self.edit, grid_region , _make_grid())

    def _puzzle(self, puzzle, state, hints):
        for row in range(0, 9):
            for col in range(0, 9):
                fill = self.cell_fill(row, col, puzzle, state, hints)
                spans = self.content(row, col)
                for span, text in zip(spans, fill):
                    self.view.replace(self.edit, span, text)

    def _hilight(self, row, col, hinting=False):
        scope = "region.yellowish" if hinting else "region.greenish"
        self.view.add_regions("sudoku_highlight", self.frame(row, col), scope,
                              flags=sublime.DRAW_NO_OUTLINE|sublime.PERSISTENT)


###----------------------------------------------------------------------------


class SudokuViewListener(sublime_plugin.ViewEventListener):
    """
    Listen for events inside of Sudoku views; we use these for specific
    handling such as key bindings as well as to block some commands that ruin
    the experience of the game.
    """
    @classmethod
    def is_applicable(cls, settings):
        return _is_sudoku(settings)

    def on_text_command(self, command, args):
        if command in ("context_menu", "drag_select", "show_scope_name",
                       "undo", "soft_undo", "redo_or_repeat"):
            return ('noop')

    def on_query_context(self, key, operator, operand, match_all):
        if key == "sudoku":
            return True == operand if operator == sublime.OP_EQUAL else False

    def on_pre_close(self):
        self.view.settings().set("window_id", self.view.window().id())

    def on_close(self):
        w = None
        w_id = self.view.settings().get("window_id")
        for window in sublime.windows():
            if window.id() == w_id:
                w = window
                break

        if not w:
            return

        # If this is the only view in this window and there are no folders open
        # in it, then close the whole window. According to the settings code in
        # the default package, we need to be careful that we don't accidentally
        # close the wrong window.
        if w.num_groups() == 1 and len(w.views_in_group(0)) == 0 and len(w.folders()) == 0:
            def close_window():
                if w.id() == sublime.active_window().id():
                    w.run_command("close_window")

            sublime.set_timeout(close_window, 50)



###----------------------------------------------------------------------------


class SudokuGameListener(sublime_plugin.EventListener):
    """
    Listen for global Sudoku events; this covers any events that a View
    listener can't listen for, such as window commands.
    """
    def on_window_command(self, window, command, args):
        if _is_sudoku(window):
            if command in ("new_file", "show_panel"):
                return ('noop')


###----------------------------------------------------------------------------
