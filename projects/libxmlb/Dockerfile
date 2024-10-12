# Copyright 2018 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
################################################################################

FROM gcr.io/oss-fuzz-base/base-builder
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        make libtool pkg-config gtk-doc-tools autotools-dev automake 

RUN pip3 install meson ninja

RUN git clone --no-checkout https://gitlab.gnome.org/GNOME/glib
RUN git -C glib checkout 1e6c6ebaa5330802910fb60256c94fd42b390038

RUN git clone --no-checkout https://github.com/hughsie/libxmlb libxmlb
RUN git -C libxmlb checkout 34d12b333bfd81209e5d657cb2db899f003eef9c

WORKDIR $SRC/libxmlb

COPY build.sh $SRC/
COPY fuzzers/ $SRC/fuzzers/
