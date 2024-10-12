
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>

#include "config.h"
#ifdef HAVE_GIO_UNIX
#include <glib-unix.h>
#endif
#include <gio/gio.h>
#include <locale.h>

#include "xb-builder.h"
#include "xb-node.h"
#include "xb-silo-export.h"
#include "xb-silo-query.h"

typedef struct {
	GCancellable *cancellable;
	GMainLoop *loop;
	GPtrArray *cmd_array;
	gboolean force;
	gboolean wait;
	gboolean profile;
	gchar **tokenize;
} XbToolPrivate;



int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {

    char filename[256];
    sprintf(filename, "/tmp/libfuzzer.xmlb");
    FILE *fp = fopen(filename, "wb");
    if (!fp) return 0;
    fwrite(data, size, 1, fp);
    fclose(fp);

    XbSiloLoadFlags flags = XB_SILO_LOAD_FLAG_NONE;
    flags |= XB_SILO_LOAD_FLAG_NO_MAGIC;

    gchar *str = NULL;
    GFile* file = g_file_new_for_path(filename);
    XbSilo* silo = xb_silo_new();
    if (xb_silo_load_from_file(silo, file, flags, NULL, NULL))
	str = xb_silo_to_string(silo, NULL);

    return 0;
}
