import sublime
import sublime_plugin


###----------------------------------------------------------------------------


# String constants for generating our grid of squares for the game board.
_grid_t = '/----v----v----\\'
_grid_b = '\\----^----^----/'
_grid_h = '>----+----+----<'
_grid_v = '|    |    |    |'

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
    Generate a game grid into the view provided, starting at the current cursor
    location in the view.
    """
    t = " ".join([_grid_t] * 3) + "\n"
    b = " ".join([_grid_b] * 3) + "\n"
    h = " ".join([_grid_h] * 3) + "\n"
    v = " ".join([_grid_v] * 3) + "\n"

    r = (t + (v * 3) + h) + ((v * 3) + h) + ((v * 3) + b)
    g = ((r + "\n") * 3) + "\n"

    return g


def _cell(view, region):
    """
    Given a region that represents the top left corner of a cell, return back
    the top left corner of the interior of that cell as a (row, col) tuple.
    """
    r, c = view.rowcol(region.a)
    return (r + 1, c + 1)


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

        view.run_command("sudoku_render", {"action": "grid"})
        view.run_command("sudoku_render", {"action": "puzzle"})

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
                self.cell_width = 6
                self.cell_height = 5

        # Dispatch the command based on the action provided.
        method = getattr(self, '_' + action)
        if method:
            return method(edit, **kwargs)

        sublime.message_dialog("Unknown Sudoku command '%s'" % action)

    def is_enabled(self, **kwargs):
        return self.view.match_selector(0, "text.plain.sudoku")

    def _span(self, pos, offset, width):
        """
        Given a position tuple of (row, col) and an offset tuple, return back a
        region that starts at the offset position and has the given width.
        """
        pos = self.view.text_point(*pos)
        pos = tuple(map(sum, zip(self.view.rowcol(pos), offset)))
        pos = self.view.text_point(*pos)

        return sublime.Region(pos, pos + width)

    def _frame(self, row, col):
        """
        Given a 0 based row and column, return back a list of regions that
        represent the frame surrounding that cell.
        """
        root = self.view.rowcol(self.cells[(row * 9) + col].begin())
        return (
            [self._span(root, (0, 0), self.cell_width)] +
            [self._span(root, (r, 0), 1) for r in range(1, self.cell_height - 1)] +
            [self._span(root, (r, self.cell_width - 1), 1) for r in range(1, self.cell_height - 1)] +
            [self._span(root, (self.cell_height - 1, 0), self.cell_width)])


    def _cell(self, region):
        """
        Given a region that represents the top left corner of a cell, return back
        the top left corner of the interior of that cell as a (row, col) tuple.
        """
        r, c = self.view.rowcol(region.a)
        return (r + 1, c + 1)

    def render(self, edit, action, **kwargs):
        """
        Invoke the sudoku render command with the given action and arguments.
        """
        kwargs["action"] = action
        self.view.run_command("sudoku_render", kwargs)


class SudokuCommand(SudokuBase, sublime_plugin.TextCommand):
    """
    This command acts as the entry point into the game logic; the action given
    is used to drive the game and the actions taken by the user.
    """
    def _new_game(self, edit):
        # These need to be settings to persist
        self.puzzle = _puzzle
        self.current_pos = (0, 0)

        self.render(edit, "grid")
        self.render(edit, "puzzle", puzzle=self.puzzle)
        self.render(edit, "hilight", row=self.current_pos[0], col=self.current_pos[1])

    def _move(self, edit, row, col):
        new_pos = (
            max(0, min(self.current_pos[0] + row, 8)),
            max(0, min(self.current_pos[1] + col, 8))
            )

        print(new_pos)
        if new_pos != self.current_pos:
            self.current_pos = new_pos
            self.render(edit, "hilight", row=new_pos[0], col=new_pos[1])


class SudokuRenderCommand(sublime_plugin.TextCommand):
    """
    Performs all "rendering" in the game view for us, based on the arguments
    provided. This allows a single command to cache the list of regions that
    know where the cells in the grid are situated.
    """
    def run(self, edit, action):
        self._setup_regions()

        method = getattr(self, '_' + action)
        if method:
            return method(edit)

        sublime.message_dialog("Unknown Sudoku render command '%s'" % action)

    def is_enabled(self, **kwargs):
        return self.view.match_selector(0, "text.plain.sudoku")

    def _setup_regions(self):
        if not hasattr(self, "cells"):
            cells = self.view.find_by_selector("meta.cell.corner")
            if cells:
                self.cells = cells

    def _grid(self, edit):
        self.view.run_command("append", {"characters": _make_grid()})

    def _puzzle(self, edit):
        idx = 0
        for row in _puzzle:
            for cell in row:
                r, c = _cell(self.view, self.cells[idx])
                idx += 1
                if cell:
                    text = str(cell) * 4

                    for offs in range(3):
                        pos = self.view.text_point(r + offs, c)
                        region = sublime.Region(pos, pos + 4)
                        self.view.replace(edit, region, text)


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
        if command in ("context_menu", "drag_select", "show_scope_name"):
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
