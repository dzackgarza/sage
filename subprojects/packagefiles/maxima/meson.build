project('maxima', 'c',
  meson_version : '>=0.63.0',
)

mod = import('unstable-external_project')

# Maxima accepts the ECL executable path. Debian's ECL package provides
# ecl-config but no pkg-config file, so discover system ECL as Sage does.
ecl_program = find_program('ecl', required: false)
ecl_config = find_program('ecl-config', required: false)
dependencies = []
if ecl_program.found() and ecl_config.found()
  ecl = ecl_program.full_path()
  ecl_version = run_command(ecl_config, '--version', check: true).stdout().strip()
else
  ecl_proj = subproject('ecl')
  ecl_dep = ecl_proj.get_variable('ecl_dep')
  ecl = ecl_dep.get_variable('ecl_bin')
  ecl_version = ecl_dep.version()
  # Carry the ECL build dependency into the external project.
  ec_lib = library(
    'ecl_lib',
    'build_dependency.c',
    dependencies : [ecl_dep.partial_dependency(sources : true)],
  )
  dependencies += [ec_lib]
endif
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
