project('maxima', 'c',
  meson_version : '>=0.63.0',
)

mod = import('unstable-external_project')

# The ECL override declared inside subprojects/packagefiles/ecl is visible
# through that subproject's exported variable, not by a sibling dependency
# lookup. Instantiate the subproject first and consume its declared dependency
# directly; this carries the staged library path and build ordering instead of
# relying on a system pkg-config entry.
ecl_proj = subproject('ecl')
ecl_dep = ecl_proj.get_variable('ecl_dep')
# The ECL subproject's override is already registered in the shared Meson
# dependency lookup; registering it again here is an error.
ecl = ecl_dep.get_variable(internal: 'ecl_bin')
ecl_version = ecl_dep.version()
# ECL's executable embeds the final ECLDIR, but Maxima invokes it before
# Meson copies staged ECL modules into the final Sage prefix. Pass the staged
# path during configure; maxima_fas_install.patch also exports it from the
# generated Makefile because the later make phase does not inherit configure's
# environment.
ecl_staged_prefix = ecl_proj.get_variable('staged_prefix')
ecl_staged_modules_dir = ecl_staged_prefix / 'lib' / ('ecl-' + ecl_version)
# Carry the ECL build dependency into the external project.
ecl_lib = library(
  'ecl_lib',
  'build_dependency.c',
  dependencies : [ecl_dep.partial_dependency(sources : true)],
)
dependencies = [ecl_lib]
staged_prefix = meson.current_build_dir() / 'dist' / get_option('prefix').strip('/')
# Match the canonical SPKG/conda side-module location, not the platform libdir
# used by Maxima's regular image tree.
ecl_side_modules_subdir = 'lib' / ('ecl-' + ecl_version)
ecl_side_modules_dir = get_option('prefix') / ecl_side_modules_subdir
# The external project's staged install is copied by Meson; the FAS
# must be in that staged tree, not directly in the final prefix.
staged_ecl_side_modules_dir = staged_prefix / ecl_side_modules_subdir
# Configure receives the final prefix; DESTDIR performs the staging.
# Supplying a staged absolute path here would stage it twice.

proj = mod.add_project('configure',
  configure_options : [
                        '--enable-ecl',
                        '--with-ecl=' + ecl,
                        # Maxima configure checks for git and, if it finds it, uses
                        # versions information from the repo. See #15529. We disable this.
                        'git_found=false',
                      ],
  env : {
    'MAXIMA_FAS_DIR': ecl_side_modules_dir,
    'SAGE_ECL_BIN': ecl,
    'ECLDIR': ecl_staged_modules_dir + '/',
  },
  depends: dependencies,
)

maxima_fas_dep = proj.dependency('maxima').partial_dependency(sources : true)
maxima_dep = declare_dependency(
  variables: {
    'MAXIMA_FAS': get_option('prefix') / ecl_side_modules_subdir / 'maxima.fas',
    'MAXIMA_PREFIX': get_option('prefix'),
    'MAXIMA_BIN': get_option('prefix') / get_option('bindir') / 'maxima',
  },
  dependencies: maxima_fas_dep
)
meson.override_dependency('maxima', maxima_dep)

subdir('build')
