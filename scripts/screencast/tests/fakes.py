"""A minimal fake of the sync Playwright API, just enough surface for
screencast.library to run against without a real browser. Shared by
test_library.py (unit, calling the library directly) and
test_driver.py/test_compose.py (which run real Robot Framework suites
against this fake through monkeypatched `playwright.sync_api`)."""


class FakeLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    @property
    def first(self):
        return self

    def scroll_into_view_if_needed(self):
        pass

    def bounding_box(self):
        return {"x": 10, "y": 10, "width": 100, "height": 20}

    def click(self):
        self.page.clicked.append(self.selector)

    def fill(self, value):
        self.page.filled[self.selector] = value

    def press_sequentially(self, text, delay=0):
        self.page.filled[self.selector] = self.page.filled.get(self.selector, "") + text

    def wait_for(self, state="visible", timeout=10000):
        pass

    def aria_snapshot(self):
        return "- generic"


class FakeMouse:
    def __init__(self):
        self.moves = []

    def move(self, x, y, steps=1):
        self.moves.append((x, y, steps))


class FakeVideo:
    def __init__(self, path):
        self._path = path

    def path(self):
        return self._path


class FakePage:
    _counter = 0

    def __init__(self, context, record):
        FakePage._counter += 1
        self.context = context
        self.url = "about:blank"
        self.mouse = FakeMouse()
        self.clicked = []
        self.filled = {}
        self.closed = False
        self.video = (
            FakeVideo(f"/tmp/fake-{FakePage._counter}.webm") if record else None
        )
        self._handlers = {}

    def goto(self, url, wait_until="load"):
        self.url = url

    def on(self, event, handler):
        self._handlers.setdefault(event, []).append(handler)

    def locator(self, selector):
        return FakeLocator(self, selector)

    def bring_to_front(self):
        pass

    def wait_for_timeout(self, ms):
        pass

    def screenshot(self, path, full_page=True):
        pass

    def is_closed(self):
        return self.closed

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, browser, **kwargs):
        self.browser = browser
        self.kwargs = kwargs
        self.init_scripts = []
        self.pages = []
        self.closed = False

    def add_init_script(self, script):
        self.init_scripts.append(script)

    def new_page(self):
        page = FakePage(self, record="record_video_dir" in self.kwargs)
        self.pages.append(page)
        return page

    def close(self):
        self.closed = True
        for page in self.pages:
            page.closed = True


class FakeChromium:
    def __init__(self, browser):
        self._browser = browser

    def launch(self, headless=True, args=None):
        return self._browser


class FakeBrowser:
    def __init__(self):
        self.contexts = []
        self.closed = False

    def new_context(self, **kwargs):
        context = FakeContext(self, **kwargs)
        self.contexts.append(context)
        return context

    def close(self):
        self.closed = True


class FakePlaywright:
    instances = []

    def __init__(self):
        self.browser = FakeBrowser()
        self.chromium = FakeChromium(self.browser)
        self.stopped = False
        FakePlaywright.instances.append(self)

    def start(self):
        return self

    def stop(self):
        self.stopped = True


def fake_sync_playwright():
    return FakePlaywright()
