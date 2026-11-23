;;; Passive status from inside AutoCAD / LT. No external COM automation.
;;; Loaded per drawing by the owned Toolkit application bundle.
(vl-load-com)
(if (not (vl-bb-ref 'mcp-toolkit-switch-serial)) (vl-bb-set 'mcp-toolkit-switch-serial 0))
(if (not *mcp-toolkit-document-id*)
  (setq *mcp-toolkit-document-id* (strcat (rtos (getvar "DATE") 2 10) "-" (itoa (getvar "MILLISECS")))))
(if (not *mcp-toolkit-phase*) (setq *mcp-toolkit-phase* "idle"))
(defun mcp-toolkit-context-write (/ app doc hwnd file tmp fp payload)
  (setq app (vlax-get-acad-object))
  (if (> (vla-get-Count (vla-get-Documents app)) 0)
    (progn
      (setq doc (vla-get-ActiveDocument app)
            hwnd (vl-princ-to-string (vla-get-HWND app))
            file (strcat *mcp-ipc-dir* "toolkit-context-" hwnd ".json")
            tmp (strcat file ".tmp"))
      (setq payload (strcat "{\"schema\":1,\"guard_protocol\":4,\"hwnd\":" hwnd
        ",\"phase\":\"" *mcp-toolkit-phase* "\""
        ",\"product\":\"" (mcp-escape-string (getvar "PROGRAM")) "\""
        ",\"version\":\"" (mcp-escape-string (getvar "ACADVER")) "\""
        ",\"document\":{\"id\":\"" *mcp-toolkit-document-id* "\",\"switch_serial\":" (itoa (vl-bb-ref 'mcp-toolkit-switch-serial)) ",\"name\":\"" (mcp-escape-string (getvar "DWGNAME")) "\""
        ",\"path\":\"" (mcp-escape-string (if (= (getvar "DWGTITLED") 1) (strcat (getvar "DWGPREFIX") (getvar "DWGNAME")) "")) "\""
        ",\"dirty\":" (if (> (getvar "DBMOD") 0) "true" "false")
        ",\"dbmod\":" (itoa (getvar "DBMOD"))
        ",\"cmdactive\":" (itoa (getvar "CMDACTIVE"))
        ",\"command\":\"" (mcp-escape-string (getvar "CMDNAMES")) "\""
        ",\"units\":" (itoa (getvar "INSUNITS"))
        ;; CommandEnded can fire before CMDACTIVE clears. Never persist that
        ;; transient bit as permanent busy state; the entry point rechecks it.
        ",\"busy\":" (if *mcp-toolkit-native-busy* "true" "false") "}}"))
      (if (setq fp (open tmp "w"))
        (progn (write-line payload fp) (close fp)
          (if (findfile file) (vl-file-delete file)) (vl-file-rename tmp file)))))
  (princ))
(defun mcp-toolkit-context-event (reactor parameters)
  (vl-catch-all-apply 'mcp-toolkit-context-write nil) (princ))
(defun mcp-toolkit-document-event (reactor parameters)
  (vl-bb-set 'mcp-toolkit-switch-serial (1+ (vl-bb-ref 'mcp-toolkit-switch-serial)))
  (mcp-toolkit-context-event reactor parameters))
(defun mcp-toolkit-command-start (reactor parameters)
  (setq *mcp-toolkit-native-busy* T)
  (mcp-toolkit-context-event reactor parameters))
(defun mcp-toolkit-command-end (reactor parameters)
  (setq *mcp-toolkit-native-busy* nil)
  (mcp-toolkit-context-event reactor parameters))
(if *mcp-toolkit-context-command-reactor* (vlr-remove *mcp-toolkit-context-command-reactor*))
(progn
  (setq *mcp-toolkit-context-command-reactor*
    (vlr-command-reactor nil '((:vlr-commandWillStart . mcp-toolkit-command-start)
      (:vlr-commandEnded . mcp-toolkit-command-end)
      (:vlr-commandCancelled . mcp-toolkit-command-end)
      (:vlr-commandFailed . mcp-toolkit-command-end)))))
(if *mcp-toolkit-context-document-reactor* (vlr-remove *mcp-toolkit-context-document-reactor*))
(progn
  (setq *mcp-toolkit-context-document-reactor*
    (vlr-docmanager-reactor nil '((:vlr-documentBecameCurrent . mcp-toolkit-document-event)))))
(vl-catch-all-apply 'mcp-toolkit-context-write nil)
(princ)
