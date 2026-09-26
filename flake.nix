{
  description = "Record, compose and verify multi-actor browser screencasts from Robot Framework stories";

  inputs.nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
      # Chromium and ffmpeg's title cards both need fonts, which a bare
      # environment (a container, a Nix build sandbox) does not have.
      fontsConf =
        pkgs:
        pkgs.makeFontsConf {
          fontDirectories = [
            pkgs.dejavu_fonts
            pkgs.liberation_ttf
          ];
        };
    in
    {
      # For another flake: `nixpkgs.overlays = [ robotframework-screencast.overlays.default ]`
      # adds `pkgs.robotframework-screencast`.
      overlays.default = final: _prev: {
        robotframework-screencast = final.callPackage ./package.nix { };
      };

      packages = forAllSystems (pkgs: rec {
        robotframework-screencast = pkgs.callPackage ./package.nix { };
        default = robotframework-screencast;
      });

      # `nix run github:datakurre/robotframework-screencast -- run story.robot`
      apps = forAllSystems (pkgs: {
        default = {
          type = "app";
          program = pkgs.lib.getExe self.packages.${pkgs.stdenv.hostPlatform.system}.default;
          meta.description = "The screencast command: run, compose and verify stories";
        };
      });

      # The engine from the working tree, with the test and docs tools:
      #   nix develop --command python -m screencast --version
      #   nix develop --command pytest
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = [
            (pkgs.python3.withPackages (
              ps: with ps; [
                robotframework
                playwright
                jsonschema
                pytest
                mkdocs
                mkdocs-material
                mkdocs-include-markdown-plugin
              ]
            ))
            pkgs.ffmpeg-headless
            pkgs.ruff
            pkgs.nixfmt-tree
          ];
          env = {
            PLAYWRIGHT_BROWSERS_PATH = "${pkgs.playwright-driver.browsers}";
            PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS = "true";
            FONTCONFIG_FILE = fontsConf pkgs;
          };
          shellHook = ''
            export PYTHONPATH="$PWD/src''${PYTHONPATH:+:$PYTHONPATH}"
          '';
        };
      });

      checks = forAllSystems (
        pkgs:
        let
          python = pkgs.python3.withPackages (
            ps: with ps; [
              robotframework
              playwright
              jsonschema
              pytest
            ]
          );
          # Run pytest over a writable copy of the sources, with the engine on
          # the path and ffmpeg for the composer and verifier tests.
          pytestCheck =
            name: args:
            pkgs.runCommand name
              {
                nativeBuildInputs = [
                  python
                  pkgs.ffmpeg-headless
                ];
                FONTCONFIG_FILE = fontsConf pkgs;
              }
              ''
                cp -r ${./.}/. source
                chmod -R u+w source
                cd source
                export HOME=$TMPDIR PYTHONPATH=$PWD/src
                pytest -p no:cacheprovider ${args}
                touch $out
              '';
          videoTests = "src/screencast/tests/test_compose.py src/screencast/tests/test_verify.py";
        in
        {
          build = self.packages.${pkgs.stdenv.hostPlatform.system}.default;

          lint = pkgs.runCommand "lint" { nativeBuildInputs = [ pkgs.ruff ]; } ''
            cp -r ${./.}/. source
            chmod -R u+w source
            cd source
            ruff check src
            ruff format --check src
            touch $out
          '';

          # Everything but the composer and verifier: seconds, no video.
          tests = pytestCheck "tests" "src/screencast/tests --ignore=src/screencast/tests/test_compose.py --ignore=src/screencast/tests/test_verify.py";

          # The composer and verifier against real ffmpeg on synthetic clips:
          # minutes.
          tests-video = pytestCheck "tests-video" videoTests;
        }
      );

      formatter = forAllSystems (pkgs: pkgs.nixfmt-tree);
    };
}
