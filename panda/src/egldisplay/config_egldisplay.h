/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file config_egldisplay.h
 * @author cary
 * @date 2009-05-21
 */

#ifndef CONFIG_EGLDISPLAY_H
#define CONFIG_EGLDISPLAY_H

#include "pandabase.h"
#include "notifyCategoryProxy.h"
#include "configVariableString.h"
#include "configVariableBool.h"
#include "configVariableInt.h"

#if defined(OPENGLES_1) && defined(OPENGLES_2)
  #error OPENGLES_1 and OPENGLES_2 cannot be defined at the same time!
#endif

// egldisplay is compiled once per GL flavor (into pandagl, pandagles or
// pandagles2), each with a different export symbol.  EXPCL_EGLDISPLAY
// resolves to the right one so that classes shared with the containing
// metalib (e.g. eglGraphicsPipe, whose type handle the metalib references)
// are exported on platforms that hide symbols by default, such as macOS.
#ifdef OPENGLES_2
  #define EXPCL_EGLDISPLAY EXPCL_PANDAGLES2

  NotifyCategoryDecl(egldisplay, EXPCL_PANDAGLES2, EXPTP_PANDAGLES2);

  extern EXPCL_PANDAGLES2 void init_libegldisplay();
  extern EXPCL_PANDAGLES2 const std::string get_egl_error_string(int error);
#elif defined(OPENGLES_1)
  #define EXPCL_EGLDISPLAY EXPCL_PANDAGLES

  NotifyCategoryDecl(egldisplay, EXPCL_PANDAGLES, EXPTP_PANDAGLES);

  extern EXPCL_PANDAGLES void init_libegldisplay();
  extern EXPCL_PANDAGLES const std::string get_egl_error_string(int error);
#else
  #define EXPCL_EGLDISPLAY EXPCL_PANDAGL

  NotifyCategoryDecl(egldisplay, EXPCL_PANDAGL, EXPTP_PANDAGL);

  extern EXPCL_PANDAGL void init_libegldisplay();
  extern EXPCL_PANDAGL const std::string get_egl_error_string(int error);
#endif

#endif
