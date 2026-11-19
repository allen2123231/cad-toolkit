;;; Passive status from inside AutoCAD / LT. No external COM automation.
;;; Loaded per drawing by the owned Toolkit application bundle.
(vl-load-com)
(defun mcp-toolkit-context-write (/ app doc hwnd file tmp fp payload)
  (setq app (vlax-get-acad-object))
  (if (> (vla-get-Count (vla-get-Documents app)) 0)
    (progn
      (setq doc (vla-get-ActiveDocument app)
            hwnd (vl-princ-to-string (vla-get-HWND app))
            file (strcat *mcp-ipc-dir* "toolkit-context-" hwnd ".json")
            tmp (strcat file ".tmp"))
      (setq payload (strcat "{\"schema\":1,\"hwnd\":" hwnd
        ",\"product\":\"" (mcp-escape-string (getvar "PROGRAM")) "\""
        ",\"version\":\"" (mcp-escape-string (getvar "ACADVER")) "\""
        ",\"document\":{\"name\":\"" (mcp-escape-string (getvar "DWGNAME")) "\""
        ",\"path\":\"" (mcp-escape-string (if (= (getvar "DWGTITLED") 1) (strcat (getvar "DWGPREFIX") (getvar "DWGNAME")) "")) "\""
        ",\"dirty\":" (if (> (getvar "DBMOD") 0) "true" "false")
        ",\"dbmod\":" (itoa (getvar "DBMOD"))
        ",\"cmdactive\":" (itoa (getvar "CMDACTIVE"))
        ",\"units\":" (itoa (getvar "INSUNITS"))
        ",\"busy\":" (if (> (getvar "CMDACTIVE") 0) "true" "false") "}}"))
      (if (setq fp (open tmp "w"))
        (progn (write-line payload fp) (close fp)
          (if (findfile file) (vl-file-delete file)) (vl-file-rename tmp file)))))
  (princ))
(defun mcp-toolkit-context-event (reactor parameters)
  (vl-catch-all-apply 'mcp-toolkit-context-write nil) (princ))
(if (not *mcp-toolkit-context-command-reactor*)
  (setq *mcp-toolkit-context-command-reactor*
    (vlr-command-reactor nil '((:vlr-commandWillStart . mcp-toolkit-context-event)
      (:vlr-commandEnded . mcp-toolkit-context-event)
      (:vlr-commandCancelled . mcp-toolkit-context-event)
      (:vlr-commandFailed . mcp-toolkit-context-event)))))
(if (not *mcp-toolkit-context-document-reactor*)
  (setq *mcp-toolkit-context-document-reactor*
    (vlr-docmanager-reactor nil '((:vlr-documentBecameCurrent . mcp-toolkit-context-event)))))
(vl-catch-all-apply 'mcp-toolkit-context-write nil)
(princ)
