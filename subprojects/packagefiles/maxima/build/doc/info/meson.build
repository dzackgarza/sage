# This file is needed in the build folder for the doc build
configure_file(
    input: '../../../doc/info/build-html-index.lisp',
    output: 'build-html-index.lisp',
    copy: true    
)

# Maxima's CL-INFO help system requires these generated index files at runtime.
# The out-of-tree Meson build must copy them from the Maxima source tree.
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
