{
  lib,
  python3Packages,
  ffmpeg-headless,
  playwright-driver,
  makeFontsConf,
  dejavu_fonts,
  liberation_ttf,
}:

let
  # The version lives in one place, src/screencast/__init__.py (hatch reads it
  # from there too).
  versionLine = lib.findFirst (line: lib.hasPrefix "__version__" line) "" (
    lib.splitString "\n" (builtins.readFile ./src/screencast/__init__.py)
  );
in
python3Packages.buildPythonApplication {
  pname = "robotframework-screencast";
  version = lib.head (lib.match ''__version__ = "(.*)"'' versionLine);
  pyproject = true;

  # Only what the build needs, so editing the docs does not rebuild it.
  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      ./pyproject.toml
      ./README.md
      ./LICENSE
      ./src
    ];
  };

  build-system = [ python3Packages.hatchling ];

  dependencies = with python3Packages; [
    robotframework
    playwright
    jsonschema
  ];

  # `screencast` records with Playwright and composes with ffmpeg: give it both,
  # and fonts, so `nix run` needs nothing else installed. Without fonts Chromium
  # lays text out at zero width, so Playwright sees empty links and cannot click
  # them, and the composer's title cards (DejaVu Sans) cannot be drawn. A
  # Chromium, PATH or fontconfig the caller already set wins
  # (SCREENCAST_CHROMIUM_PATH points at a specific build).
  makeWrapperArgs = [
    "--prefix"
    "PATH"
    ":"
    (lib.makeBinPath [ ffmpeg-headless ])
    "--set-default"
    "PLAYWRIGHT_BROWSERS_PATH"
    "${playwright-driver.browsers}"
    "--set-default"
    "PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS"
    "true"
    "--set-default"
    "FONTCONFIG_FILE"
    "${makeFontsConf {
      fontDirectories = [
        dejavu_fonts
        liberation_ttf
      ];
    }}"
  ];

  # The suite takes minutes (it encodes real video): it runs as the flake's
  # `checks` instead, so `nix build` stays fast.
  doCheck = false;
  pythonImportsCheck = [ "screencast" ];

  meta = {
    description = "Record, compose and verify multi-actor browser screencasts from Robot Framework stories";
    homepage = "https://github.com/datakurre/robotframework-screencast";
    license = lib.licenses.gpl2Only;
    mainProgram = "screencast";
    platforms = lib.platforms.linux;
  };
}
