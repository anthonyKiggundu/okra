{{- define "oai-core-cn5g.componentLabels" -}}
app.kubernetes.io/name: oai-core-cn5g
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}
