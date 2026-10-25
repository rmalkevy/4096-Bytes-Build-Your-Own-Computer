; fact(n): аргумент в A, результат в A. Псує B.
        LOADI A, 5
        CALL  fact
        OUTN
        HALT
fact:   LOADI B, 0
        CMP   A, B
        JZ    base
        LOADI B, 1
        CMP   A, B
        JZ    base
        PUSH  A
        DEC   A
        CALL  fact
        POP   B
        MUL   A, B
        RET
base:   LOADI A, 1
        RET
