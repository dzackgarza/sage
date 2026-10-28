# This file is needed in the build folder for the doc build
configure_file(
    input: '../../../doc/info/build-html-index.lisp',
    output: 'build-html-index.lisp',
    copy: true    
)

# The Maxima release tarball ships these generated help indexes in its source
# tree. Sage's out-of-tree Meson build must copy them to build/doc/info, where
# CL-INFO resolves them through the configured Maxima prefix.
configure_file(
    input: '../../../doc/info/maxima-index.lisp',
    output: 'maxima-index.lisp',
    copy: true,
)
configure_file(
    input: '../../../doc/info/maxima-index-html.lisp',
    output: 'maxima-index-html.lisp',
    copy: true,
)
