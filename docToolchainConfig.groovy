outputPath = 'build'

inputPath = 'src/docs'

inputFiles = [
    [file: 'index.adoc',                                    formats: ['html5']],
    [file: 'arc42/arc42.adoc',                              formats: ['html5']],
    [file: 'specs/prd.adoc',                                formats: ['html5']],
    [file: 'specs/business-rules.adoc',                     formats: ['html5']],
    [file: 'specs/uc-01-ausleihe.adoc',                     formats: ['html5']],
    [file: 'specs/uc-02-verlaengerung.adoc',                formats: ['html5']],
    [file: 'specs/uc-03-rueckgabe.adoc',                    formats: ['html5']],
    [file: 'specs/uc-04-pruefprotokoll.adoc',               formats: ['html5']],
    [file: 'specs/uc-05-vormerkung.adoc',                   formats: ['html5']],
    [file: 'specs/uc-06-wartung.adoc',                      formats: ['html5']],
    [file: 'specs/uc-07-verloren.adoc',                     formats: ['html5']],
    [file: 'specs/uc-08-katalog.adoc',                      formats: ['html5']],
    [file: 'specs/uc-09-einweisung.adoc',                   formats: ['html5']],
    [file: 'specs/supplementary-entity-model.adoc',         formats: ['html5']],
    [file: 'specs/supplementary-interface-contract.adoc',   formats: ['html5']],
    [file: 'specs/supplementary-validation-rules.adoc',     formats: ['html5']],
    [file: 'specs/supplementary-system-events.adoc',        formats: ['html5']],
]

taskInputsDirs = []
taskInputsFiles = []
