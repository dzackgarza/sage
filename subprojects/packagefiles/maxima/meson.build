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
# Maxima 5.47.0's Meson entry point independently calls dependency('ecl').
# Export the staged dependency into the parent/subproject lookup scope; passing
# it only to the external-project wrapper does not satisfy that lookup.
meson.override_dependency('ecl', ecl_dep)
ecl = ecl_dep.get_variable(internal: 'ecl_bin')
ecl_version = ecl_dep.version()
# Carry the ECL build dependency into the external project.
ecl_lib = library(
  'ecl_lib',
  'build_dependency.c',
  dependencies : [ecl_dep.partial_dependency(sources : true)],
)
dependencies = [ecl_lib]
staged_prefix = meson.current_build_dir() + '/dist' + get_option('prefix')
# Match the canonical SPKG/conda side-module location, not the platform libdir
# used by Maxima's regular image tree.
ecl_side_modules_subdir = 'lib' / ('ecl-' + ecl_version)
ecl_side_modules_dir = get_option('prefix') / ecl_side_modules_subdir

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
  },
  depends: dependencies,
)

maxima_fas_dep = proj.dependency('maxima').partial_dependency(sources : true)
maxima_dep = declare_dependency(
  variables: {
    'MAXIMA_FAS': staged_prefix / ecl_side_modules_subdir / 'maxima.fas',
    'MAXIMA_PREFIX': staged_prefix,
    'MAXIMA_BIN': staged_prefix / get_option('bindir') / 'maxima',
  },
  dependencies: maxima_fas_dep
)
meson.override_dependency('maxima', maxima_dep)

subdir('build')
