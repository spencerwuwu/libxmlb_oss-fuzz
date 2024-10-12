
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
    sprintf(filename, "/tmp/libfuzzer.xml");
    FILE *fp = fopen(filename, "wb");
    if (!fp) return 0;
    fwrite(data, size/2, 1, fp);
    fclose(fp);

    size_t msg_len = size - size/2;
    char* msg = malloc(msg_len+1);
    memcpy(msg, data+size/2, msg_len);
    msg[size/2] = '\0';


    const gchar *const *locales = g_get_language_names();
    XbBuilder* builder = xb_builder_new();
    XbSilo* silo = NULL;
    GFile* file_dst = NULL;

    /* load file */
    for (guint i = 0; locales[i] != NULL; i++)
	xb_builder_add_locale(builder, locales[i]);

    GFile* file = g_file_new_for_path(filename);
    XbBuilderSource* source = xb_builder_source_new();
    //if (priv->tokenize != NULL) {
    //    XbBuilderFixup* fixup = NULL;
    //    fixup = xb_builder_fixup_new("TextTokenize",
    //    		      xb_tool_builder_tokenize_cb,
    //    		      priv,
    //    		      NULL);
    //    xb_builder_source_add_fixup(source, fixup);
    //}
    if (!xb_builder_source_load_file(source,
				     file,
				     XB_BUILDER_SOURCE_FLAG_WATCH_FILE |
				     XB_BUILDER_SOURCE_FLAG_LITERAL_TEXT,
				     NULL,
				     NULL))
	return 0;
    xb_builder_import_source(builder, source);

    /* Compile */
    file_dst = g_file_new_for_path("/tmp/libfuzzer.xmlb");
    xb_builder_set_profile_flags(builder,
				 XB_SILO_PROFILE_FLAG_APPEND);
    silo = xb_builder_ensure(builder,
			     file_dst,
			     XB_BUILDER_COMPILE_FLAG_WATCH_BLOB |
				 XB_BUILDER_COMPILE_FLAG_IGNORE_INVALID |
				 XB_BUILDER_COMPILE_FLAG_NATIVE_LANGS,
			     NULL,
			     NULL);
    if (silo) {
	GPtrArray* results = NULL;
	XbQuery* query = NULL;
	XbQueryContext* context = XB_QUERY_CONTEXT_INIT();

	/* query */
	query = xb_query_new_full(silo, msg, XB_QUERY_FLAG_OPTIMIZE, NULL);
	if (query == NULL)
	    return 0;
	results = xb_silo_query_with_context(silo, query, &context, NULL);
	if (!results)
	    return 0;
	for (guint i = 0; i < results->len; i++) {
	    XbNode *n = g_ptr_array_index(results, i);
	    gchar *xml = NULL;
	    xml = xb_node_export(n,
			  XB_NODE_EXPORT_FLAG_FORMAT_MULTILINE |
			  XB_NODE_EXPORT_FLAG_FORMAT_INDENT,
			  NULL);
	}
    }

    return 0;
}

