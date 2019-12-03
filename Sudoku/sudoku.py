import sublime
import sublime_plugin


###----------------------------------------------------------------------------


# String constants for generating our grid of squares for the game board.
_grid_h = '+----+----+----+'
_grid_v = '|    |    |    |'


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


def _make_grid(view):
    """
    Generate a game grid into the view provided, starting at the current cursor
    location in the view.
    """
    h = " ".join([_grid_h] * 3) + "\n"
    v = " ".join([_grid_v] * 3) + "\n"
    r = ((h + (v * 3)) * 3) + h
    g = ((r + "\n") * 3) + "\n"

    view.run_command("append", {"characters": g})


###----------------------------------------------------------------------------


class SudokuNewGame(sublime_plugin.ApplicationCommand):
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

        _make_grid(view)

        # Finalize it now; from this point forward we need to adjust the read
        # only state in order to modify the view.
        view.set_read_only(True)
        view.sel().clear()


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
