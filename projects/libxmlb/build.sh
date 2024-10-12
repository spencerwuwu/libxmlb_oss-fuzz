#!/bin/bash -eu

export CFLAGS="$CFLAGS -gdwarf-4     -fPIC"
export CXXFLAGS="$CXXFLAGS -gdwarf-4 -fPIC"


PREFIX=$WORK/prefix
mkdir -p $PREFIX

export PKG_CONFIG="`which pkg-config` --static"
export PKG_CONFIG_PATH=$PREFIX/lib/pkgconfig
export PATH=$PREFIX/bin:$PATH

BUILD=$WORK/build

rm -rf $WORK/*
rm -rf $BUILD
mkdir -p $BUILD

## build glib
pushd $SRC/glib/
meson \
    --prefix=$PREFIX \
    --libdir=lib \
    --default-library=static \
    -Db_lundef=false \
    -Doss_fuzz=enabled \
    -Dlibmount=disabled \
    _builddir
ninja -C _builddir
ninja -C _builddir install
popd

# build libxmlb
meson \
    --prefix=$PREFIX \
    --default-library=static \
    -Dintrospection=false \
    -Dgtkdoc=false \
    -Dtests=false \
    -Dstemmer=false \
    -Dlzma=disabled \
    _builddir
ninja -C _builddir
ninja -C _builddir install

find . -name "*.a"

DEPS="glib-2.0 gio-2.0"

PREDEPS_LDFLAGS="-Wl,-Bdynamic -ldl -lm -lc -pthread -lrt -lpthread"

BUILD_CFLAGS="$CFLAGS `pkg-config --static --cflags $DEPS`"
BUILD_LDFLAGS="-Wl,-static `pkg-config --static --libs $DEPS`"

fuzzers=$(find $SRC/fuzzers/ -name "*.c")
for f in $fuzzers; do
    fuzzer_name=$(basename $f .c)
    $CC $BUILD_CFLAGS $LIB_FUZZING_ENGINE \
            -I src \
            -I _builddir \
            ${f} \
            -c -o ${fuzzer_name}.o

    $CXX $CXXFLAGS \
            ${fuzzer_name}.o -o $OUT/${fuzzer_name} \
            -L/work/prefix/lib/x86_64-linux-gnu -lxmlb\
            $PREDEPS_LDFLAGS \
            $BUILD_LDFLAGS \
            -I src \
            -I _builddir \
            -gdwarf-4 \
            $LIB_FUZZING_ENGINE \
            -Wl,-Bdynamic
done
