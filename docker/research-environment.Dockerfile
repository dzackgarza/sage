# syntax=docker/dockerfile:1

FROM debian:trixie AS base

ENV DEBIAN_FRONTEND=noninteractive
ENV GIT_CEILING_DIRECTORIES=/sage/subprojects

RUN printf '%s\n' \
      'path-exclude=/usr/share/doc/*' \
      'path-include=/usr/share/doc/*/copyright' \
      'path-exclude=/usr/share/man/*' \
      'path-exclude=/usr/share/info/*' \
      'path-exclude=/usr/share/texmf/doc/*' \
      'path-exclude=/usr/share/texlive/texmf-dist/doc/*' \
      > /etc/dpkg/dpkg.cfg.d/01-nodoc

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git \
 && rm -rf /var/lib/apt/lists/*

ENV UV_INSTALL_DIR=/usr/local/bin \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    UV_PYTHON_BIN_DIR=/usr/local/bin \
    UV_NO_MODIFY_PATH=1
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
 && uv python install --default 3.14 \
 && test "$(command -v python3)" = /usr/local/bin/python3 \
 && curl -LsSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin

COPY build /sage/build
COPY pyproject.toml configure.ac /sage/
WORKDIR /sage

RUN set -eu; \
    packages="$(build/bin/sage-get-system-packages debian $(build/bin/sage-package list :standard:) \
        | tr ' ' '\n' | grep -vxE 'libbrial-dev|libbrial-groebner-dev|gap|libgap.*|gap-.*' | tr '\n' ' ')"; \
    if [ -z "$packages" ]; then \
        echo "FATAL: Sage's package metadata produced no Debian packages" >&2; exit 1; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends $packages; \
    rm -rf /var/lib/apt/lists/*; \
    if ! command -v gcc >/dev/null; then \
        echo "FATAL: no C compiler after installing Sage's prerequisites" >&2; exit 1; \
    fi

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    libbliss-dev libhomfly-dev librw-dev \
    macaulay2 \
    4ti2 latte-int lrslib topcom msolve normaliz-bin libnormaliz-dev \
    polymake libpolymake-dev libgiac-dev xcas fricas kissat cliquer \
    sagemath-database-graphs sagemath-database-polytopes \
    pari-galdata pari-elldata pari-seadata pari-galpol \
    graphviz dvipng imagemagick \
    cmake libpcre2-dev cargo rustc ccache rsync binutils-gold \
 && rm -rf /var/lib/apt/lists/*

RUN apt-get update \
 && apt-get install -y texlive-full pdf2svg poppler-utils nodejs unzip xz-utils \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

RUN set -eu; \
    sha256=586c380a4ab18638ce6e8a0e865b6a0b450fa2317b45cadf3e682867e9e433cf; \
    curl -fsSL --output /tmp/luahyperbolic.zip \
        "https://ftp.gwdg.de/pub/ctan/macros/luatex/latex/luahyperbolic.zip"; \
    echo "$sha256  /tmp/luahyperbolic.zip" | sha256sum -c -; \
    mkdir -p /usr/local/share/texmf/tex/lualatex; \
    unzip -q /tmp/luahyperbolic.zip -d /usr/local/share/texmf/tex/lualatex; \
    rm -f /tmp/luahyperbolic.zip; \
    mktexlsr /usr/local/share/texmf; \
    kpsewhich luahyperbolic.sty

RUN set -eu; \
    version=1.11.9; \
    sha256=64078d1623d9ab89da766591f3410a0756f3737a37efb0897c7e84b863bf092a; \
    curl -fsSL -o /tmp/quarto.deb \
        "https://github.com/quarto-dev/quarto-cli/releases/download/v${version}/quarto-${version}-linux-amd64.deb"; \
    echo "$sha256  /tmp/quarto.deb" | sha256sum -c -; \
    apt-get update; \
    apt-get install -y /tmp/quarto.deb; \
    rm -f /tmp/quarto.deb; \
    rm -rf /var/lib/apt/lists/*; \
    test -x /usr/local/bin/quarto; \
    echo "quarto $(quarto --version)"; \
    test "$(quarto --version)" = "${version}"

RUN set -eu; \
    version=3.14; \
    sha256=dedb81f20345b76d7168ba551d90abceb707977fece789a79874094fe3833915; \
    curl -fsSL -o /tmp/pandoc.deb \
        "https://github.com/jgm/pandoc/releases/download/${version}/pandoc-${version}-1-amd64.deb"; \
    echo "$sha256  /tmp/pandoc.deb" | sha256sum -c -; \
    apt-get update; \
    apt-get install -y /tmp/pandoc.deb; \
    rm -f /tmp/pandoc.deb; \
    rm -rf /var/lib/apt/lists/*; \
    test "$(command -v pandoc)" = /usr/bin/pandoc; \
    test "$(pandoc --version | head -n 1)" = "pandoc ${version}"

RUN uv venv /sage/.venv --python 3.14

ENV PKG_CONFIG_PATH=/sage/.venv/lib/pkgconfig

ENV NORMALIZ_LOCAL_DIR=/sage/.venv

RUN set -eu; \
    SAGE_LOCAL=/sage/.venv; \
    version="$(cat build/pkgs/gap/package-version.txt)"; \
    sha256="$(sed -n 's/^sha256=//p' build/pkgs/gap/checksums.ini)"; \
    curl -fsSL -o /tmp/gap.tar.gz "https://github.com/gap-system/gap/releases/download/v${version}/gap-${version}.tar.gz"; \
    echo "${sha256}  /tmp/gap.tar.gz" | sha256sum -c -; \
    mkdir /tmp/gap; tar -xzf /tmp/gap.tar.gz -C /tmp/gap --strip-components=1; \
    cd /tmp/gap; \
    ./configure --prefix="$SAGE_LOCAL"; \
    make -j"$(nproc)"; \
    make install; \
    test -x "$SAGE_LOCAL/bin/gap" && test -f "$SAGE_LOCAL/lib/gap/sysinfo.gap"; \
    GAP_ROOT_PKG="$SAGE_LOCAL/lib/gap/pkg"; \
    mkdir -p "$GAP_ROOT_PKG"; \
    cp -a /tmp/gap/pkg/. "$GAP_ROOT_PKG/"; \
    echo "installed $(ls "$GAP_ROOT_PKG" | wc -l) GAP packages"; \
    compiled_old="cohomolo crypting grape orb datastructures"; \
    compiled_new="nq io digraphs"; \
    for pkg in $compiled_old; do \
        echo "building GAP package $pkg"; \
        cd "$GAP_ROOT_PKG/$pkg" && ./configure "$SAGE_LOCAL/lib/gap" && make -j"$(nproc)" && cd /; \
    done; \
    echo "building GAP package guava"; \
    export CFLAGS="-std=gnu17 -Wno-implicit-function-declaration ${CFLAGS:-}"; \
    cd "$GAP_ROOT_PKG/guava" && ./configure "$SAGE_LOCAL/lib/gap" && make -j"$(nproc)" && cd /; \
    for pkg in $compiled_new; do \
        echo "building GAP package $pkg"; \
        cd "$GAP_ROOT_PKG/$pkg" && ./configure --with-gaproot="$SAGE_LOCAL/lib/gap" && make -j"$(nproc)" && cd /; \
    done; \
    cd /; rm -rf /tmp/gap /tmp/gap.tar.gz; \
    printf '%s\n' "$SAGE_LOCAL/lib" > /etc/ld.so.conf.d/sage-local.conf; \
    ldconfig; \
    "$SAGE_LOCAL/bin/gap" -q --nointeract -c 'for n in ["atlasrep", "design", "grape", "guava", "hap", "polenta", "polycyclic", "sonata", "io", "alnuth", "orb", "forms", "genss", "recog"] do if LoadPackage(n) <> true then Print("FATAL: GAP package ", n, " does not load\n"); QUIT_GAP(1); fi; od;'

COPY --chmod=0755 docker/gap-launcher.sh /usr/local/bin/gap
COPY --chmod=0755 docker/gap-launcher.sh /usr/bin/gap

RUN set -eu; \
    for prefix in 4ti2- latte- topcom-; do \
        for program in /usr/bin/"$prefix"*; do \
            name="${program#/usr/bin/$prefix}"; \
            if [ "$prefix$name" = latte-minimize ]; then continue; fi; \
            ln -s "$program" /usr/local/bin/"$name"; \
        done; \
    done; \
    command -v hilbert count points2allfinetriangs

RUN set -eu; \
    version="$(cat build/pkgs/libbraiding/package-version.txt)"; \
    sha256="$(sed -n 's/^sha256=//p' build/pkgs/libbraiding/checksums.ini)"; \
    curl -fsSL -o /tmp/libbraiding.tar.gz "https://github.com/miguelmarco/libbraiding/releases/download/$version/libbraiding-$version.tar.gz"; \
    echo "$sha256  /tmp/libbraiding.tar.gz" | sha256sum -c -; \
    mkdir /tmp/libbraiding; tar -xzf /tmp/libbraiding.tar.gz -C /tmp/libbraiding --strip-components=1; \
    cd /tmp/libbraiding; ./configure --prefix=/usr/local; make -j"$(nproc)"; make install; ldconfig; \
    rm -rf /tmp/libbraiding /tmp/libbraiding.tar.gz; \
    pkg-config --atleast-version=1.3.1 libbraiding

RUN set -eu; \
    curl -fsSL -o /tmp/pcre.tar.bz2 https://sourceforge.net/projects/pcre/files/pcre/8.45/pcre-8.45.tar.bz2/download; \
    echo "4dae6fdcd2bb0bb6c37b5f97c33c2be954da743985369cddac3546e3218bffb8  /tmp/pcre.tar.bz2" | sha256sum -c -; \
    mkdir /tmp/pcre; tar -xjf /tmp/pcre.tar.bz2 -C /tmp/pcre --strip-components=1; \
    cd /tmp/pcre; ./configure --prefix=/opt/pcre --disable-shared --enable-utf --enable-unicode-properties; \
    make -j"$(nproc)"; make install; \
    git clone https://github.com/rgugliel/CoxIter /tmp/coxiter; \
    git -C /tmp/coxiter -c advice.detachedHead=false checkout b800be48d8240fbabd2d1c9542e61054584ad7fe; \
    cmake -S /tmp/coxiter -B /tmp/coxiter/build -DCMAKE_PREFIX_PATH=/opt/pcre -DCMAKE_CXX_FLAGS=-I/opt/pcre/include -DCMAKE_INSTALL_PREFIX=/usr/local; \
    cmake --build /tmp/coxiter/build -j"$(nproc)"; \
    cmake --install /tmp/coxiter/build; \
    rm -rf /tmp/pcre /tmp/pcre.tar.bz2 /tmp/coxiter; \
    command -v coxiter

RUN set -eu; \
    SAGE_LOCAL=/sage/.venv; \
    version="$(cat build/pkgs/normaliz/package-version.txt)"; \
    sha256="$(sed -n 's/^sha256=//p' build/pkgs/normaliz/checksums.ini)"; \
    curl -fsSL -o /tmp/normaliz.tar.gz "https://github.com/Normaliz/Normaliz/releases/download/v${version}/normaliz-${version}.tar.gz"; \
    echo "${sha256}  /tmp/normaliz.tar.gz" | sha256sum -c -; \
    mkdir /tmp/normaliz; tar -xzf /tmp/normaliz.tar.gz -C /tmp/normaliz --strip-components=1; \
    cd /tmp/normaliz; \
    export ac_cv_lib_flint_fmpz_poly_set_coeff_mpz=yes; \
    ./configure --prefix="$SAGE_LOCAL" --with-flint --with-e-antic --with-nauty; \
    make -j"$(nproc)"; \
    make install; \
    test -f "$SAGE_LOCAL/lib/libnormaliz.so" && test -f "$SAGE_LOCAL/include/libnormaliz/cone.h"; \
    test -x "$SAGE_LOCAL/bin/normaliz" && "$SAGE_LOCAL/bin/normaliz" -v | head -1; \
    cd /; rm -rf /tmp/normaliz /tmp/normaliz.tar.gz

RUN set -eu; \
    SAGE_LOCAL=/sage/.venv; \
    sha256="02651d99c391007d384b3fadbc20abc6916b77036f9e496c99e9ce8688ca4b53"; \
    curl -fsSL -o /tmp/pari.tar.gz "https://pari.math.u-bordeaux.fr/pub/pari/unix/pari-2.17.4.tar.gz"; \
    echo "${sha256}  /tmp/pari.tar.gz" | sha256sum -c -; \
    mkdir /tmp/pari; tar -xzf /tmp/pari.tar.gz -C /tmp/pari --strip-components=1; \
    cd /tmp/pari; \
    export LANG=C; \
    bash ./Configure --prefix="$SAGE_LOCAL" --mt=pthread --kernel=gmp --graphic=none; \
    make -j"$(nproc)" gp; \
    make install -j1; \
    ldconfig; \
    test -f "$SAGE_LOCAL/lib/libpari-gmp-tls.so.9" && test -x "$SAGE_LOCAL/bin/gp"; \
    "$SAGE_LOCAL/bin/gp" --version | head -1; \
    test -f "$SAGE_LOCAL/include/pari/pari.h"; \
    cd /; rm -rf /tmp/pari /tmp/pari.tar.gz

FROM base AS environment

RUN set -eu; \
    curl -LsSf -o /tmp/julia.tar.gz https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.7-linux-x86_64.tar.gz; \
    echo "4e7e9e776634d24835250de67cde39b0d4af15bc432eb20697e6be6c28ea69e8  /tmp/julia.tar.gz" | sha256sum -c -; \
    mkdir /opt/julia; \
    tar -xzf /tmp/julia.tar.gz -C /opt/julia --strip-components=1; \
    rm /tmp/julia.tar.gz; \
    test -x /opt/julia/bin/julia; \
    test -f /opt/julia/lib/julia/sys.so; \
    test "$(/opt/julia/bin/julia --startup-file=no -e 'print(Sys.BINDIR)')" = /opt/julia/bin; \
    echo "julia $(/opt/julia/bin/julia --version) with its sysimage at /opt/julia/lib/julia/sys.so"

COPY --chmod=0755 docker/julia-launcher.sh /usr/local/bin/julia

ENV JULIA_DEPOT_PATH=/opt/julia-depot: \
    JULIA_CPU_TARGET=generic \
    JULIA_BINDIR=/opt/julia/bin \
    PYTHON_JULIAPKG_EXE=/opt/julia/bin/julia

RUN set -eu; \
    julia --startup-file=no --color=no -e ' \
        using Pkg; \
        Pkg.add(["Oscar", "JSON"]); \
        Pkg.precompile(); \
        import JSON; \
        using Oscar; \
        println("JSON ", pkgversion(JSON), ", Oscar ", Oscar.VERSION_NUMBER, " loaded")'; \
    chmod -R a+rX /opt/julia-depot

ENV SAGE_BIN=/sage/.venv/bin/sage
ENV PATH=/sage/.venv/bin:$PATH

COPY . /sage

ENV CCACHE_DIR=/ccache

ENV ELAN_HOME=/opt/elan
ENV PATH=/opt/elan/bin:$PATH
RUN curl -sSfL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh \
    | sh -s -- -y --no-modify-path --default-toolchain none \
 && elan --version

ARG MATHLIB_REVISION=

RUN --mount=type=cache,target=/ccache \
    echo "mathlib head for this build: ${MATHLIB_REVISION:-read by the provisioning script}" \
 && just research-environment-venv
RUN --mount=type=cache,target=/ccache \
    just research-environment-sage && ccache --show-stats

ARG RESEARCH_REVISIONS=
RUN --mount=type=cache,target=/ccache just research-environment-repositories
RUN --mount=type=cache,target=/ccache just research-environment-lean \
 && rm -rf /root/.cache/mathlib
RUN --mount=type=cache,target=/ccache \
    just research-environment-pip-check && ccache --show-stats

RUN set -eu; \
    jl="$(command -v julia)"; \
    HOME=/root /sage/.venv/bin/python -c 'import juliapkg; juliapkg.resolve()'; \
    chmod -R a+rX /opt/julia-depot; \
    echo "depot resolved at build time against $("$jl" --version)"

FROM scratch AS lock
COPY --from=environment /sage/uv.lock /uv.lock

FROM environment

RUN "$SAGE_BIN" docker/research-environment-check.py
