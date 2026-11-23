;;; Fenced execution, loaded AFTER the pinned dispatcher's command whitelist.
;;; Reactor callbacks only observe; commands execute from this explicit entry.
(defun mcp-toolkit-phase-write (request-id phase / file fp)
  (setq *mcp-toolkit-phase* phase)
  (setq file (strcat *mcp-ipc-dir* "toolkit-receipt-" request-id ".json"))
  (if (setq fp (open (strcat file ".tmp") "w"))
    (progn
      (write-line (strcat "{\"request_id\":\"" request-id "\",\"phase\":\"" phase
        "\",\"document_id\":\"" *mcp-toolkit-document-id* "\"}") fp)
      (close fp) (if (findfile file) (vl-file-delete file))
      (vl-file-rename (strcat file ".tmp") file)))
  (vl-catch-all-apply 'mcp-toolkit-context-write nil))

(defun c:mcp-dispatch (/ files file text request-id cmd result result-file old-osmode old-cmdecho)
  (setq files (vl-directory-files *mcp-ipc-dir* "autocad_mcp_cmd_*.json" 1))
  ;; Never choose arbitrarily among competing/legacy mailboxes.
  (if (= (length files) 1)
    (progn
      (setq file (strcat *mcp-ipc-dir* (car files)) text (mcp-read-file-lines file))
      (setq request-id (mcp-json-get-string text "request_id") cmd (mcp-json-get-string text "command"))
      (if (and request-id cmd)
        (progn
          (setq result-file (strcat *mcp-ipc-dir* "autocad_mcp_result_" request-id ".json"))
          (cond
            ((findfile (strcat *mcp-ipc-dir* "toolkit-revoked-" request-id ".json"))
              (vl-file-delete file)
              (mcp-write-result result-file request-id nil nil "REVOKED_REQUEST_NOT_EXECUTED"))
            ((findfile (strcat *mcp-ipc-dir* "toolkit-recovery.json"))
              (vl-file-delete file)
              (mcp-write-result result-file request-id nil nil "RECOVERY_BARRIER_NOT_EXECUTED"))
            ((or (/= (mcp-json-get-number text "toolkit_protocol") 2)
                 (/= (mcp-json-get-number text "toolkit_hwnd") (vla-get-HWND (vlax-get-acad-object)))
                 (/= (mcp-json-get-string text "toolkit_document") *mcp-toolkit-document-id*))
              (vl-file-delete file)
              (mcp-write-result result-file request-id nil nil "TARGET_DOCUMENT_CHANGED_NOT_EXECUTED"))
            ((or *mcp-toolkit-native-busy* (> (getvar "CMDACTIVE") 0))
              (vl-file-delete file)
              (mcp-write-result result-file request-id nil nil "CAD_BUSY_NOT_EXECUTED"))
            (T
              (vl-file-delete file)
              (mcp-toolkit-phase-write request-id "claimed")
              (setq old-osmode (getvar "OSMODE") old-cmdecho (getvar "CMDECHO"))
              (setvar "OSMODE" 0) (setvar "CMDECHO" 0)
              (mcp-toolkit-phase-write request-id "executing")
              (setq result (vl-catch-all-apply 'mcp-dispatch-command (list cmd text)))
              ;; No ESC, retries, or implicit completion of interactive commands.
              (setvar "OSMODE" old-osmode) (setvar "CMDECHO" old-cmdecho)
              (if (vl-catch-all-error-p result) (setq result (cons nil (vl-catch-all-error-message result))))
              (if (= 1 (logand 1 (getvar "CMDACTIVE")))
                ;; The operation left an interactive prompt. Its modifications
                ;; are uncertain: do not claim completion or send ESC for it.
                (mcp-toolkit-phase-write request-id "waiting_input")
                (progn
                  (if (car result)
                    (mcp-write-result result-file request-id T (cdr result) nil)
                    (mcp-write-result result-file request-id nil nil (cdr result)))
                  (mcp-toolkit-phase-write request-id "completed")
                  (setq *mcp-toolkit-phase* "idle")
                  (vl-catch-all-apply 'mcp-toolkit-context-write nil)))))))))
  (princ))

;;; Native recovery is a maintenance entry, never a dispatcher for drawing code.
(defun mcp-toolkit-valid-key (key / i valid char)
  (setq valid (and key (> (strlen key) 0) (<= (strlen key) 80)) i 1)
  (while (and valid (<= i (strlen key)))
    (setq char (ascii (substr key i 1)))
    (if (not (or (and (>= char 48) (<= char 57)) (and (>= char 65) (<= char 90))
                 (and (>= char 97) (<= char 122)) (= char 45) (= char 95))) (setq valid nil))
    (setq i (1+ i)))
  valid)
;;; Check inactive documents too: a command may be suspended in another tab.
;;; An unavailable document API fails closed (including unsupported LT builds).
(defun mcp-toolkit-all-documents-idle (/ docs result idle doc value active)
  (setq idle T
        result (vl-catch-all-apply 'vla-get-Documents (list (vlax-get-acad-object))))
  (if (vl-catch-all-error-p result) (setq idle nil)
    (progn
      (setq docs result)
      (vlax-for doc docs
        (setq value (vl-catch-all-apply 'vla-GetVariable (list doc "CMDACTIVE")))
        (if (vl-catch-all-error-p value) (setq idle nil)
          (progn
            (if (= (type value) 'VARIANT) (setq value (vlax-variant-value value)))
            ;; COM sees our maintenance LISP as bit 32 in the active document.
            ;; Ignore ONLY that bit there; suspended LISP in another tab blocks.
            (setq active (vl-catch-all-apply 'vla-get-Active (list doc)))
            (if (and (eq active :vlax-true) (numberp value)) (setq value (logand value 223)))
            (if (or (not (numberp value)) (/= value 0)) (setq idle nil)))))))
  idle)
(defun c:mcp-recover (/ files file text request-id old-key result-file recovery revoked fp payload application-idle initial-serial)
  (setq initial-serial (vl-bb-ref 'mcp-toolkit-switch-serial))
  (setq files (vl-directory-files *mcp-ipc-dir* "autocad_mcp_recover_*.json" 1))
  (if (= (length files) 1)
    (progn
      (setq file (strcat *mcp-ipc-dir* (car files)) text (mcp-read-file-lines file)
            request-id (mcp-json-get-string text "request_id") old-key (mcp-json-get-string text "fence_request_id"))
      (if (and (mcp-toolkit-valid-key request-id) (mcp-toolkit-valid-key old-key))
        (progn
          (setq result-file (strcat *mcp-ipc-dir* "autocad_mcp_result_" request-id ".json")
                recovery (strcat *mcp-ipc-dir* "toolkit-recovery.json"))
          (vl-file-delete file)
          (cond
            ((or (not (findfile recovery)) (/= old-key (mcp-json-get-string (mcp-read-file-lines recovery) "request_id")))
              (mcp-write-result result-file request-id nil nil "RECOVERY_TARGET_CHANGED"))
            ((or (/= (mcp-json-get-number text "toolkit_protocol") 4)
                 (/= (mcp-json-get-number text "toolkit_hwnd") (vla-get-HWND (vlax-get-acad-object)))
                 (/= (mcp-json-get-string text "toolkit_document") *mcp-toolkit-document-id*))
              (mcp-write-result result-file request-id nil nil "TARGET_DOCUMENT_CHANGED_NOT_EXECUTED"))
            ((or *mcp-toolkit-native-busy* (> (getvar "CMDACTIVE") 0))
              (mcp-write-result result-file request-id nil nil "CAD_BUSY_NOT_EXECUTED"))
            ((and (eq (mcp-json-get-number text "require_application_idle") 1)
                  (not (eq (mcp-json-get-number text "expected_switch_serial") initial-serial)))
              (mcp-write-result result-file request-id nil nil "RECOVERY_TARGET_CHANGED"))
            ((and (eq (mcp-json-get-number text "require_application_idle") 1)
                  (not (setq application-idle (mcp-toolkit-all-documents-idle))))
              (mcp-write-result result-file request-id nil nil "RECOVERY_DOCUMENT_BUSY_OR_UNVERIFIED"))
            (T
              (setq revoked (strcat *mcp-ipc-dir* "toolkit-revoked-" old-key ".json")
                    payload (strcat "{\"request_id\":\"" old-key "\",\"probe_id\":\"" request-id "\"}"))
              (if (setq fp (open (strcat revoked ".tmp") "w"))
                (progn
                  (write-line payload fp) (close fp)
                  (if (findfile revoked) (vl-file-delete revoked))
                  (if (vl-file-rename (strcat revoked ".tmp") revoked)
                    (mcp-write-result result-file request-id T
                      (strcat "{\"fenced_request_id\":\"" old-key "\",\"document_id\":\"" *mcp-toolkit-document-id* "\",\"probe_id\":\"" request-id "\",\"application_idle\":" (if application-idle "true" "false") ",\"initial_switch_serial\":" (itoa initial-serial) ",\"verified_switch_serial\":" (itoa (vl-bb-ref 'mcp-toolkit-switch-serial)) "}") nil)
                    (mcp-write-result result-file request-id nil nil "RECOVERY_FENCE_WRITE_FAILED")))
                (mcp-write-result result-file request-id nil nil "RECOVERY_FENCE_WRITE_FAILED"))))))))
  (princ))
(princ)

;;; Separate entry and inbox: never touches write mail or changes drawing vars.
;;; A delayed read notification cannot accidentally dispatch abandoned writes.
(defun c:mcp-read (/ files file text request-id cmd result result-file)
  (setq files (vl-directory-files *mcp-ipc-dir* "autocad_mcp_read_*.json" 1))
  (if (= (length files) 1)
    (progn
      (setq file (strcat *mcp-ipc-dir* (car files)) text (mcp-read-file-lines file)
            request-id (mcp-json-get-string text "request_id") cmd (mcp-json-get-string text "command"))
      (if (and request-id cmd)
        (progn
          (setq result-file (strcat *mcp-ipc-dir* "autocad_mcp_result_" request-id ".json"))
          (vl-file-delete file)
          (cond
            ((not (member cmd '("ping" "drawing-info" "drawing-get-variables" "entity-count" "entity-list" "entity-get" "layer-list" "block-list" "block-get-attributes")))
              (mcp-write-result result-file request-id nil nil "READ_OPERATION_NOT_ALLOWED"))
            ((or (/= (mcp-json-get-number text "toolkit_protocol") 3)
                 (/= (mcp-json-get-number text "toolkit_hwnd") (vla-get-HWND (vlax-get-acad-object)))
                 (/= (mcp-json-get-string text "toolkit_document") *mcp-toolkit-document-id*))
              (mcp-write-result result-file request-id nil nil "TARGET_DOCUMENT_CHANGED_NOT_EXECUTED"))
            ((or *mcp-toolkit-native-busy* (> (getvar "CMDACTIVE") 0))
              (mcp-write-result result-file request-id nil nil "CAD_BUSY_NOT_EXECUTED"))
            (T
              (setq result (vl-catch-all-apply 'mcp-dispatch-command (list cmd text)))
              (if (vl-catch-all-error-p result) (setq result (cons nil (vl-catch-all-error-message result))))
              (if (car result)
                (mcp-write-result result-file request-id T (cdr result) nil)
                (mcp-write-result result-file request-id nil nil (cdr result)))))))))
  (princ))
